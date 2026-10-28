"""Builds a structured CaseAnalysis from case documents.

The LLM only extracts facts (LlmCaseFacts). Everything that is arithmetic over the law
(ч. 1 ст. 62 limit, "within sanction") is computed here.
"""

import json
import logging
import math

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    ImposedPunishment,
    ImposedSentence,
    MeasureUnit,
    SanctionCeiling,
)
from legal_core.rules.imposed_term import check_imposed_imprisonment, check_imposed_punishment
from legal_core.rules.sanction_ceiling import sanction_ceiling_for_part
from pydantic import ValidationError

from src.application.practice_report import PracticeReport
from src.schemas.analysis import (
    AnalysisStats,
    CaseAnalysis,
    ImposedCountRead,
    ImposedSentenceRead,
    LegalCheck,
    LlmCaseFacts,
    PracticeComparisonRead,
    PrecedentFilterRead,
    PrecedentMatchRead,
    SentenceScale,
    SimilarVerdictRef,
)
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.legal_checks import build_legal_checks
from src.services.llm_client import LLMClient, LLMError
from src.services.sanction_summary import (
    describe_main_alternatives,
    describe_term,
    format_amount,
)
from src.services.sentence_checks import build_sentence_checks
from src.services.sentencing import art62_part1_limit

logger = logging.getLogger(__name__)

DOCUMENT_CHARS_LIMIT = 30000
DEFAULT_QUESTION = "Подготовь проект приговора: квалификация, обстоятельства, варианты наказания."

SYSTEM_PROMPT = """Ты — ассистент судьи по уголовным делам (УК РФ).
По материалам дела извлеки факты.
Отвечай ТОЛЬКО JSON-объектом без пояснений, строго по схеме:
{schema}
Правила:
- Сроки — целые месяцы.
- sanction_max_months — максимальный срок лишения свободы по санкции квалифицирующей части статьи.
- В norm указывай норму в виде «п. «и» ч. 1 ст. 61».
- legal_facts: каждое значение сопровождай точной цитатой quote из материалов дела или вопроса.
- Для рецидива prior_convictions: одна запись на отдельный приговор, не на статью.
- Поля каждой записи: judgment_id (дата/номер приговора), guilt (intentional/negligent),
  category (small/medium/grave/especially_grave), adult_at_offence, active_at_offence,
  convicted_before_offence, imprisoned_by_sentence, conditional_or_deferred,
  revoked_and_sent_before_offence. Все поля — объекты value/quote. Неизвестные поля пропускай.
- history_complete=true только при явном полном описании судимостей или указании «ранее не судим».
- category и sanction_max_months без подтверждения в материалах не заполняй.
- legal_facts.imposed_imprisonment_months — срок лишения свободы, назначенный в резолютивной
  части проекта приговора (целые месяцы; при условном осуждении тоже), quote — точный фрагмент
  с этим сроком. legal_facts.art64_applied — true только при явной ссылке на ст. 64 УК РФ.
- Если сведений нет — null или пустой список, ничего не выдумывай."""


def build_user_prompt(
    question: str | None, document_texts: list[str], similar_items: list[dict]
) -> str:
    documents = "\n\n---\n\n".join(t for t in document_texts if t.strip())[:DOCUMENT_CHARS_LIMIT]
    similar = "\n".join(
        f"- {item.get('case_number') or 'без номера'}: {item.get('excerpt')}"
        for item in similar_items
    )
    return (
        f"Вопрос:\n{question or DEFAULT_QUESTION}\n\n"
        f"Материалы дела:\n{documents or 'Материалы не переданы.'}\n\n"
        f"Похожие приговоры из базы знаний:\n{similar or 'Не найдены.'}"
    )


def _similar_refs(similar_items: list[dict]) -> list[SimilarVerdictRef]:
    refs = []
    for item in similar_items:
        score = item.get("score")
        refs.append(
            SimilarVerdictRef(
                verdict_id=item.get("verdict_id"),
                # Punishment is not extracted from knowledge-base verdicts yet (next iteration).
                punishment=item.get("case_number") or "Приговор без номера",
                court=" · ".join(x for x in [item.get("court_name"), item.get("verdict_date")] if x)
                or "Суд не указан",
                match=(item.get("excerpt") or "")[:160],
                score=round(score * 100) if isinstance(score, int | float) else 0,
            )
        )
    return refs


def _precedent_punishment(months: int | None, conditional: bool) -> str:
    if months is None:
        return "Наказание не распознано"
    term = f"{format_amount(months, MeasureUnit.MONTHS)} лишения свободы"
    return f"{term}, условно" if conditional else term


def precedent_prompt_items(report: PracticeReport) -> list[dict]:
    """The comparable precedents in the shape the LLM prompt lists them."""
    return [
        {
            "verdict_id": item.stored.knowledge_verdict_id,
            "case_number": item.stored.uid,
            "court_name": item.stored.court_name,
            "verdict_date": item.stored.decision_date.isoformat()
            if item.stored.decision_date
            else None,
            "excerpt": "; ".join(
                [
                    ", ".join(str(e.qualification) for e in item.stored.card.episodes),
                    _precedent_punishment(
                        item.stored.card.imprisonment_months, item.stored.card.conditional
                    ),
                ]
            ),
            "score": item.score,
        }
        for item in report.shown
    ]


def _precedent_reads(report: PracticeReport) -> list[PrecedentMatchRead]:
    return [
        PrecedentMatchRead(
            card_id=item.stored.id,
            court_name=item.stored.court_name,
            decision_date=item.stored.decision_date.isoformat()
            if item.stored.decision_date
            else None,
            uid=item.stored.uid,
            source_url=item.stored.source_url,
            qualifications=[str(e.qualification) for e in item.stored.card.episodes],
            punishment_months=item.stored.card.imprisonment_months,
            conditional=item.stored.card.conditional,
            recidivism=item.stored.card.recidivism.value if item.stored.card.recidivism else None,
            score=item.score,
            breakdown=item.breakdown,
            filters=[
                PrecedentFilterRead(
                    name=f.name, state=f.state.value, reason=f.reason, action=f.action.value
                )
                for f in item.filters
            ],
            channels=list(item.channels),
        )
        for item in report.shown
    ]


def _practice_read(report: PracticeReport) -> PracticeComparisonRead:
    c = report.comparison
    return PracticeComparisonRead(
        total=c.total,
        with_term=c.with_term,
        enough_data=c.enough_data,
        min_months=c.min_months,
        p25_months=c.p25_months,
        median_months=c.median_months,
        p75_months=c.p75_months,
        max_months=c.max_months,
        conditional_share=c.conditional_share,
        art64_share=c.art64_share,
        art73_share=c.art73_share,
        draft_months=c.draft_months,
        draft_percentile=c.draft_percentile,
        position=c.position.value if c.position else None,
        candidates=report.candidates,
        excluded=report.excluded,
        vector_used=report.vector_used,
    )


def _precedent_refs(report: PracticeReport) -> list[SimilarVerdictRef]:
    return [
        SimilarVerdictRef(
            verdict_id=item.stored.knowledge_verdict_id,
            punishment=_precedent_punishment(
                item.stored.card.imprisonment_months, item.stored.card.conditional
            ),
            court=" · ".join(
                x
                for x in [
                    item.stored.court_name,
                    item.stored.decision_date.isoformat() if item.stored.decision_date else None,
                ]
                if x
            )
            or "Суд не указан",
            match=", ".join(str(e.qualification) for e in item.stored.card.episodes)[:160],
            score=round(item.score * 100),
        )
        for item in report.shown
    ]


def assemble_analysis(
    facts: LlmCaseFacts,
    *,
    prompt: str,
    documents: int,
    pages: int,
    seconds: int,
    similar_items: list[dict],
    extra_warnings: list[str],
    document_texts: list[str] | None = None,
    statute: StatuteSanctionReading | None = None,
    sentence: ImposedSentence | None = None,
    count_statutes: dict[ArticleReference, StatuteSanctionReading] | None = None,
    model_texts: list[str] | None = None,
    practice: PracticeReport | None = None,
    precedent_source: str | None = None,
) -> CaseAnalysis:
    """sentence/count_statutes come from the operative part read by regex; when present, the
    imposed punishment is checked per count instead of the single model-cited term.
    practice holds the precedent cards found for the draft and the T28 comparison."""
    warnings = list(extra_warnings)
    per_count = sentence is not None and bool(sentence.counts)
    ceiling = _statutory_ceiling(statute)
    sanction_max_months = facts.sanction_max_months
    statute_checks: list[LegalCheck] = []
    if _single_part(statute):
        statute_checks.append(_statute_sanction_check(statute))
    elif statute is not None:
        warnings.append(
            "В квалификации не указана часть статьи — санкция по тексту УК РФ не применена."
        )
    if ceiling is not None and ceiling.max_imprisonment_months is not None:
        statutory_max = ceiling.max_imprisonment_months
        if sanction_max_months and sanction_max_months != statutory_max:
            warnings.append(
                f"Модель указала максимум санкции {sanction_max_months} мес., по тексту УК РФ — "
                f"{statutory_max} мес.; использовано значение из текста УК РФ."
            )
        sanction_max_months = statutory_max
    prompt_texts = model_texts if model_texts is not None else document_texts or []
    context_size = len("\n\n---\n\n".join(t for t in prompt_texts if t.strip()))
    if model_texts is not None and sum(map(len, model_texts)) < sum(map(len, document_texts or [])):
        warnings.append(
            "Для модели сокращена описательная часть; вводная и резолютивная части "
            "переданы полностью."
        )
    if context_size > DOCUMENT_CHARS_LIMIT:
        warnings.append(
            f"Модели передано не больше {DOCUMENT_CHARS_LIMIT} символов; "
            f"{context_size - DOCUMENT_CHARS_LIMIT} символов не вошли. "
            "Анализ охватывает документы не полностью."
        )
    # Quotes are accepted only from what the model actually saw.
    source_text = "\n".join(
        [
            prompt,
            "\n\n---\n\n".join(t for t in prompt_texts if t.strip())[:DOCUMENT_CHARS_LIMIT],
        ]
    )
    art62_limit = (
        art62_part1_limit(sanction_max_months, facts.mitigating, facts.aggravating)
        if sanction_max_months
        else None
    )
    if per_count:
        statute_checks = _count_checks(sentence, count_statutes or {}, facts)
    elif _single_part(statute):
        statute_checks.append(
            _imposed_term_check(statute, facts.legal_facts, source_text, art62_limit)
        )
    scale = None
    if sanction_max_months:
        limit = art62_limit
        rec = facts.recommended_months
        cap = limit if limit is not None else sanction_max_months
        scale = SentenceScale(
            sanction_max_months=sanction_max_months,
            limit_months=limit,
            limit_norm="ч. 1 ст. 62" if limit is not None else None,
            recommended_months=rec,
            within_sanction=(rec <= cap) if rec is not None else None,
        )
        comparison = practice.comparison if practice is not None else None
        if comparison is not None and comparison.enough_data:
            # Half up, not Python's half-to-even: 13.5 and 28.5 must both move outward alike.
            scale.practice_months = (
                math.floor(comparison.p25_months + 0.5),
                math.floor(comparison.p75_months + 0.5),
            )
            scale.avg_similar_months = math.floor(comparison.median_months + 0.5)
        if ceiling is not None and ceiling.max_imprisonment_months is not None:
            warnings.append(_statute_warning(statute))
        else:
            warnings.append(
                "Максимум санкции определён моделью и пока не сверен со справочником УК РФ."
            )
        if rec is not None and rec > cap:
            warnings.append("Рекомендованный срок выходит за допустимый предел — проверьте.")

    legal_checks = statute_checks + build_legal_checks(
        facts.legal_facts,
        source_text,
        statutory_ceiling=ceiling,
    )
    cited_guilt = facts.legal_facts.guilt if facts.legal_facts is not None else None
    legal_checks += build_sentence_checks(
        sentence,
        count_statutes or {},
        legal_checks,
        facts.mitigating,
        document_text="\n".join(document_texts or []),
        guilt=cited_guilt.value if cited_guilt is not None else None,
    )
    return CaseAnalysis(
        legal_checks=legal_checks,
        imposed_sentence=_sentence_read(sentence),
        stats=AnalysisStats(documents=documents, pages=pages, seconds=seconds),
        prompt=prompt,
        fabula=facts.fabula,
        qualification=facts.qualification,
        scale=scale,
        mitigating=facts.mitigating,
        aggravating="; ".join(f"{c.name} — {c.norm}" for c in facts.aggravating)
        or "Не установлены (ст. 63 УК РФ).",
        personality=facts.personality,
        variants=facts.variants,
        similar=_precedent_refs(practice)
        if practice and practice.shown
        else _similar_refs(similar_items),
        precedent_source=precedent_source,
        precedents=_precedent_reads(practice) if practice else [],
        practice=_practice_read(practice) if practice else None,
        warnings=warnings,
    )


def _single_part(statute: StatuteSanctionReading | None) -> bool:
    return statute is not None and len({s.part for s in statute.sanctions}) == 1


def _statutory_ceiling(statute: StatuteSanctionReading | None) -> SanctionCeiling | None:
    if not _single_part(statute):
        return None
    return sanction_ceiling_for_part(statute.sanctions, statute.sanctions[0].part)


def _statute_warning(statute: StatuteSanctionReading) -> str:
    source = statute.provenance
    return (
        f"Санкция прочитана из текста УК РФ («{source.edition_label}», {source.source_url}); "
        f"статус редакции: {source.verification_status}. Сверьте редакцию на дату деяния."
    )


def _statute_sanction_check(statute: StatuteSanctionReading) -> LegalCheck:
    first = statute.sanctions[0]
    reference = ArticleReference(article=first.article, part=first.part)
    return LegalCheck(
        norm=f"Санкция {reference}",
        status="ok",
        value=describe_main_alternatives(statute.sanctions),
        source=statute.provenance.source_url,
        explanation=(
            "Основные виды наказания по тексту статьи из импортированной редакции УК РФ. "
            "Это техническое чтение текста: редакция не проверена юристом."
        ),
        evidence=[first.clause],
    )


def _count_checks(
    sentence: ImposedSentence,
    statutes: dict[ArticleReference, StatuteSanctionReading],
    facts: LlmCaseFacts,
) -> list[LegalCheck]:
    """Sanction and imposed-punishment checks for every count of the operative part."""
    checks: list[LegalCheck] = []
    seen_sanctions: set[ArticleReference] = set()
    for count in sentence.counts:
        reading = statutes.get(count.reference) if count.reference else None
        if not _single_part(reading):
            checks.append(_unchecked_count(count))
            continue
        if count.reference not in seen_sanctions:
            seen_sanctions.add(count.reference)
            checks.append(_statute_sanction_check(reading))
        ceiling = _statutory_ceiling(reading)
        limit = None
        if ceiling is not None and ceiling.max_imprisonment_months:
            limit = art62_part1_limit(
                ceiling.max_imprisonment_months, facts.mitigating, facts.aggravating
            )
        result = check_imposed_punishment(
            count.main,
            reading.sanctions,
            source=reading.provenance.source_url,
            art62_limit_months=limit,
        )
        checks.append(
            LegalCheck(
                norm=f"{result.norm} · {count.qualification}",
                status=result.status.value,
                explanation=result.explanation,
                source=result.source,
                value=describe_term(count.main),
                evidence=[count.quote] if count.quote else [],
            )
        )
    if sentence.final is not None:
        checks.append(
            LegalCheck(
                norm=f"Окончательное наказание ({sentence.aggregation_rule or 'ст. 69/70 УК РФ'})",
                status="insufficient_data",
                value=describe_term(sentence.final),
                source="ст. 69, 70 УК РФ",
                explanation=(
                    "Окончательное наказание прочитано из резолютивной части; правила сложения "
                    "наказаний по ст. 69 и 70 УК РФ пока не проверяются."
                ),
                evidence=[sentence.final_quote] if sentence.final_quote else [],
            )
        )
    return checks


def _unchecked_count(count: CountSentence) -> LegalCheck:
    return LegalCheck(
        norm=f"Назначенное наказание · {count.qualification or 'эпизод без квалификации'}",
        status="insufficient_data",
        value=describe_term(count.main),
        source="",
        explanation=(
            "Санкция для этой квалификации не найдена в импортированном тексте УК РФ "
            "или в квалификации не указана часть статьи."
        ),
        evidence=[count.quote] if count.quote else [],
    )


def _sentence_read(sentence: ImposedSentence | None) -> ImposedSentenceRead | None:
    if sentence is None or sentence.is_empty:
        return None
    return ImposedSentenceRead(
        counts=[
            ImposedCountRead(
                qualification=c.qualification,
                punishment=describe_term(c.main),
                additional=[describe_term(a) for a in c.additional],
                imprisonment_months=c.main.imprisonment_months,
                quote=c.quote,
            )
            for c in sentence.counts
        ],
        final=describe_term(sentence.final) if sentence.final else None,
        aggregation_rule=sentence.aggregation_rule,
        conditional=sentence.conditional,
        probation_months=sentence.probation_months,
        final_quote=sentence.final_quote or None,
    )


def _cited(fact, source_text: str, kind: type):
    """Value of a model fact only when its quote is literally present in the materials."""
    if fact is None or fact.quote not in source_text or type(fact.value) is not kind:
        return None
    return fact.value


def _imposed_term_check(
    statute: StatuteSanctionReading,
    legal_facts,
    source_text: str,
    art62_limit: int | None,
) -> LegalCheck:
    imposed = _cited(getattr(legal_facts, "imposed_imprisonment_months", None), source_text, int)
    art64 = _cited(getattr(legal_facts, "art64_applied", None), source_text, bool)
    if imposed is not None and imposed <= 0:
        imposed = None
    result = check_imposed_imprisonment(
        ImposedPunishment(imposed),
        statute.sanctions,
        source=statute.provenance.source_url,
        art62_limit_months=art62_limit,
        art64_applied=bool(art64),
    )
    evidence = [legal_facts.imposed_imprisonment_months.quote] if imposed is not None else []
    return LegalCheck(
        norm=result.norm,
        status=result.status.value,
        explanation=result.explanation,
        source=result.source,
        value=f"{imposed} мес." if imposed is not None else None,
        evidence=evidence,
    )


async def extract_facts(
    llm: LLMClient,
    question: str | None,
    document_texts: list[str],
    similar_items: list[dict],
) -> LlmCaseFacts:
    system = SYSTEM_PROMPT.format(
        schema=json.dumps(LlmCaseFacts.model_json_schema(), ensure_ascii=False)
    )
    user = build_user_prompt(question, document_texts, similar_items)

    last_error: Exception | None = None
    for attempt in (1, 2):  # one retry for malformed output
        data = await llm.complete_json(system, user)
        try:
            return LlmCaseFacts.model_validate(data)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "LLM output failed validation (attempt %s): %s", attempt, exc.error_count()
            )
    raise LLMError("Ответ модели не соответствует схеме анализа") from last_error
