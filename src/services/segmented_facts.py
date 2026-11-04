"""Translate model DTOs to cited domain observations and back to the existing result DTO.

Small inputs keep the existing single-call behavior. Long inputs are read in full windows;
local model recommendations are never presented as recommendations for the whole case.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.application.anonymization import identifier_spans
from src.application.segmented_extraction import extract_document_segments
from src.domain.analysis_segments import (
    MODEL_DOCUMENT_CHARS,
    AnalysisSegment,
    segment_documents,
)
from src.domain.cited_facts import CitedCandidate, SegmentFacts
from src.domain.extraction import input_hash
from src.infrastructure.identifier_detector import detect_identifiers
from src.schemas.analysis import (
    Circumstance,
    CitedFact,
    ExtractedFactRead,
    ExtractionDocumentRead,
    ExtractionRead,
    ExtractionSegmentRead,
    LegalFacts,
    LlmCaseFacts,
    Qualification,
)

WindowReader = Callable[..., Awaitable[LlmCaseFacts]]


@dataclass(frozen=True)
class CaseExtraction:
    facts: LlmCaseFacts
    extraction: ExtractionRead
    warnings: tuple[str, ...]


def _read_candidates(
    facts: LlmCaseFacts, sources: tuple[AnalysisSegment, ...], question: str
) -> SegmentFacts:
    candidates, rejected = [], []
    if question:
        sources = (*sources, AnalysisSegment(-1, input_hash(question), 0, len(question), question))

    def add(path, value, quote):
        if quote:
            for source in sources:
                offset = source.text.find(quote)
                if offset >= 0:
                    start = source.start + offset
                    candidates.append(
                        CitedCandidate(
                            path,
                            value,
                            quote,
                            source.document_index,
                            source.document_hash,
                            start,
                            start + len(quote),
                        )
                    )
                    return
        rejected.append(" / ".join(path))

    if facts.legal_facts:
        for name in LegalFacts.model_fields:
            if name == "prior_convictions":
                continue
            fact = getattr(facts.legal_facts, name)
            if fact is not None:
                add((name,), fact.value, fact.quote)
        for prior in facts.legal_facts.prior_convictions:
            identity = prior.get("judgment_id")
            if identity is None or type(identity.value) is not str or not identity.value.strip():
                rejected.append("prior_convictions / judgment_id")
                continue
            for name, fact in prior.items():
                add(("prior_convictions", identity.value, name), fact.value, fact.quote)
    for name in ("mitigating", "aggravating"):
        for item in getattr(facts, name):
            add((name, item.norm, item.name), True, item.quote)
    qualification = facts.qualification
    return SegmentFacts(
        summary=facts.fabula,
        candidates=tuple(candidates),
        rejected=tuple(rejected),
        qualification=(qualification.article, qualification.title) if qualification else None,
        personality=facts.personality,
    )


def _coverage(texts, segments, readings, conflicts):
    return ExtractionRead(
        complete=True,
        documents=[
            ExtractionDocumentRead(
                document_index=index, document_hash=input_hash(text), characters=len(text)
            )
            for index, text in enumerate(texts)
        ],
        segments=[
            ExtractionSegmentRead(
                document_index=s.document_index,
                document_hash=s.document_hash,
                start=s.start,
                end=s.end,
            )
            for s in segments
        ],
        facts=[
            ExtractedFactRead(
                path=list(c.path),
                value=c.value,
                quote=c.quote,
                document_index=c.document_index,
                document_hash=c.document_hash,
                start=c.start,
                end=c.end,
            )
            for reading in readings
            for c in reading.candidates
        ],
        conflicts=[" / ".join(path) for path in conflicts],
        rejected=list(dict.fromkeys(path for reading in readings for path in reading.rejected)),
    )


async def extract_case_segments(
    llm,
    question: str | None,
    texts: list[str],
    similar_items: list[dict],
    *,
    window_reader: WindowReader,
    evidence_question: str | None = None,
) -> CaseExtraction:
    question = question or ""
    # Conversation history may guide the model but previous assistant answers are not evidence.
    evidence_question = question if evidence_question is None else evidence_question
    # This limit counts the same separators as the existing prompt builder.
    if len("\n\n---\n\n".join(t for t in texts if t.strip())) <= MODEL_DOCUMENT_CHARS:
        facts = await window_reader(llm, question, texts, similar_items)
        segments = segment_documents(texts)
        reading = _read_candidates(facts, segments, evidence_question)
        return CaseExtraction(facts, _coverage(texts, segments, (reading,), ()), ())

    async def read(segment: AnalysisSegment) -> SegmentFacts:
        fragment_question = (
            f"{question}\n\nСейчас передан только фрагмент документа. Извлеки факты "
            "с цитатами из него; отсутствие факта во фрагменте не доказывает его "
            "отсутствия в деле. Не составляй рекомендацию по делу целиком: "
            "recommended_months=null, variants=[]."
        )
        facts = await window_reader(llm, fragment_question, [segment.text], similar_items)
        return _read_candidates(facts, (segment,), evidence_question)

    protected = identifier_spans((*texts, question), detect_identifiers)[:-1]
    result = await extract_document_segments(texts, read, protected=protected)
    readings = result.readings
    coverage = _coverage(texts, result.segments, readings, result.merged.conflicts)
    legal = {}
    priors: dict[str, dict[str, CitedFact]] = {}
    circumstances = {"mitigating": {}, "aggravating": {}}
    for candidate in result.merged.accepted:
        path = candidate.path
        fact = CitedFact(value=candidate.value, quote=candidate.quote)
        if path[0] == "prior_convictions":
            priors.setdefault(path[1], {})[path[2]] = fact
        elif path[0] in circumstances:
            circumstances[path[0]].setdefault(
                path[1], Circumstance(name=path[2], norm=path[1], quote=candidate.quote)
            )
        else:
            legal[path[0]] = fact
    legal["prior_convictions"] = list(priors.values())
    qualifications = dict.fromkeys(r.qualification for r in readings if r.qualification)
    qualification = next(iter(qualifications)) if len(qualifications) == 1 else None
    warnings = [
        "Все сегменты документов переданы модели. Выводы отдельных фрагментов "
        "не использованы как рекомендация по делу целиком."
    ]
    if "history_complete" not in legal and any(
        candidate.path == ("history_complete",)
        for reading in readings
        for candidate in reading.candidates
    ):
        warnings.append("Полнота истории судимостей по совокупности фрагментов не подтверждена.")
    if coverage.conflicts:
        warnings.append(
            "В извлечённых фактах есть противоречия между сегментами; спорные значения "
            "исключены из расчётов и требуют проверки."
        )
    if coverage.rejected:
        warnings.append(
            "Часть фактов модели не подтверждена цитатой в прочитанном сегменте "
            "и исключена; требуется проверка оригинала."
        )
    if len(qualifications) > 1:
        warnings.append(
            "В сегментах прочитаны разные квалификации; единственная квалификация "
            "по ответу модели не выбрана. Наказания проверяются по эпизодам из текста."
        )
    facts = LlmCaseFacts(
        fabula="\n\n".join(dict.fromkeys(r.summary for r in readings if r.summary)),
        qualification=Qualification(article=qualification[0], title=qualification[1])
        if qualification
        else None,
        personality="\n".join(dict.fromkeys(r.personality for r in readings if r.personality))
        or None,
        legal_facts=LegalFacts(**legal),
        mitigating=list(circumstances["mitigating"].values()),
        aggravating=list(circumstances["aggravating"].values()),
    )
    return CaseExtraction(facts, coverage, tuple(warnings))
