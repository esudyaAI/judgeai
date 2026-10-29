"""Builds a structured CaseAnalysis from case documents.

The LLM only extracts facts (LlmCaseFacts). Everything that is arithmetic over the law
(ч. 1 ст. 62 limit, "within sanction") is computed here.
"""

import json
import logging
import math
import re
import time
from dataclasses import replace

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    Guilt,
    ImposedPunishment,
    ImposedSentence,
    PunishmentKind,
    SanctionCeiling,
)
from legal_core.rules.aggregate import check_final_term
from legal_core.rules.art15 import categorize
from legal_core.rules.art62 import part1_limit_amount
from legal_core.rules.art66 import NORMS as ART66_NORMS
from legal_core.rules.art66 import SOURCE as ART66_SOURCE
from legal_core.rules.art66 import reduced_maximum
from legal_core.rules.imposed_term import (
    check_imposed_imprisonment,
    check_imposed_punishment,
    most_severe_alternative,
)
from legal_core.rules.sanction_ceiling import sanction_ceiling_for_part
from legal_core.rules.sentence_edges import (
    check_additional,
    check_additional_aggregate,
    check_article69_part,
    check_article70,
    check_other_aggregate,
    check_prior_chronology,
)
from pydantic import ValidationError

from src.application.practice_report import PracticeReport
from src.infrastructure.circumstance_extractor import extract_circumstances
from src.schemas.analysis import (
    AnalysisStats,
    CaseAnalysis,
    DefendantAnalysisRead,
    ImposedCountRead,
    ImposedSentenceRead,
    LegalCheck,
    LlmCaseFacts,
    PracticeComparisonRead,
    PrecedentFilterRead,
    PrecedentMatchRead,
    PunishmentVariant,
    Qualification,
    SentenceScale,
    SimilarVerdictRef,
)
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.defendant_blocks import scoped_verdicts
from src.services.legal_checks import build_legal_checks, guilt_from_text
from src.services.llm_client import LLMClient, LLMError
from src.services.punishment_extractor import (
    extract_imposed_sentence,
    read_chronology,
    read_prior_terms,
)
from src.services.sanction_summary import (
    describe_main_alternatives,
    describe_precedent_punishment,
    describe_term,
)
from src.services.sentence_checks import build_sentence_checks
from src.services.sentencing import art62_part1_limit
from src.services.verdict_segmenter import segment_verdict
from src.services.verified_circumstances import (
    confirmed_no_aggravating,
    read_court_circumstances,
    verified_circumstances,
)

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
- qualification.article — все статьи обвинения или приговора через «; », при покушении или
  приготовлении — вместе со ст. 30 («ч. 3 ст. 30, ч. 1 ст. 161 УК РФ»).
- mitigating и aggravating — только обстоятельства, которые суд признал. Если в тексте сказано,
  что обстоятельство «не усматривается», «не установлено» или «не признаётся», не включай его.
- В пользовательских текстах не используй служебные имена полей: final_sentence называй
  «окончательное наказание»; variants[].label — короткое название по-русски (1–3 слова),
  без ключей вроде offense_1 или aggregate_crimes.
- У каждого mitigating/aggravating указывай точную quote из положительного вывода суда.
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
                    describe_precedent_punishment(
                        item.stored.card.punishment, item.stored.card.conditional
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
        qualification=str(report.query.main_qualification)
        if report.query.main_qualification
        else None,
        recidivism=report.query.recidivism.value if report.query.recidivism else None,
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
            punishment=describe_precedent_punishment(
                item.stored.card.punishment, item.stored.card.conditional
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
    defendant_practice: dict[int, PracticeReport] | None = None,
) -> CaseAnalysis:
    """sentence/count_statutes come from the operative part read by regex; when present, the
    imposed punishment is checked per count instead of the single model-cited term.
    practice holds the precedent cards found for the draft and the T28 comparison."""
    warnings = list(extra_warnings)
    full_text = "\n\n".join(document_texts or [])
    people = [person for text in (document_texts or []) for person in scoped_verdicts(text)]
    if people:
        individual = []
        for index, (person, text) in enumerate(people):
            # Global model facts cannot be attributed to any person without a subject contract.
            own_facts = LlmCaseFacts(fabula=facts.fabula)
            own_parts = segment_verdict(text)
            own_extraction = extract_imposed_sentence(own_parts.operative, own_parts.description)
            own_sentence = own_extraction.sentence
            own_warnings = (
                ["Не все наказания прочитаны; нераспознанные назначения требуют ручной сверки."]
                if own_extraction.ambiguous_windows or own_sentence.is_empty
                else []
            )
            own = assemble_analysis(
                own_facts,
                prompt="",
                documents=documents,
                pages=pages,
                seconds=seconds,
                similar_items=[],
                extra_warnings=own_warnings,
                document_texts=[text],
                sentence=own_sentence,
                count_statutes=count_statutes,
                practice=(defendant_practice or {}).get(index),
                precedent_source=precedent_source,
            )
            display_person = person.upper() if person.startswith("фио") else person.title()
            individual.append(
                DefendantAnalysisRead(
                    label=f"Осуждённый {index + 1}: {display_person}",
                    legal_checks=own.legal_checks,
                    imposed_sentence=own.imposed_sentence,
                    mitigating=own.mitigating,
                    aggravating=own.aggravating,
                    practice_episodes=own.practice_episodes,
                    similar=own.similar,
                    warnings=own.warnings,
                )
            )
        return CaseAnalysis(
            stats=AnalysisStats(documents=documents, pages=pages, seconds=seconds),
            prompt=prompt,
            fabula=facts.fabula,
            defendants=individual,
            warnings=[
                *warnings,
                "Проверки разделены по осуждённым. Непривязанные "
                "факты модели не использованы для персональных расчётов.",
            ],
        )

    mitigating, rejected_m = verified_circumstances(facts.mitigating, full_text, mitigating=True)
    aggravating, rejected_a = verified_circumstances(facts.aggravating, full_text, mitigating=False)
    facts = facts.model_copy(update={"mitigating": mitigating, "aggravating": aggravating})
    if rejected_m or rejected_a:
        warnings.append(
            "Часть обстоятельств модели не подтверждена положительным выводом суда "
            "с цитатой; они исключены из расчётов и требуют проверки."
        )

    if sentence is not None and sentence.unserved is None:
        balance, balance_quote, _, _ = read_prior_terms(full_text)
        if balance is not None:
            sentence = replace(sentence, unserved=balance, unserved_quote=balance_quote)
    if sentence is not None and sentence.prior_judgment_date is None:
        prior, prior_quote, credit, credit_quote = read_chronology(full_text)
        sentence = replace(
            sentence,
            prior_judgment_date=prior,
            prior_judgment_quote=prior_quote,
            credited=sentence.credited or credit,
            credited_quote=sentence.credited_quote or credit_quote,
        )
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
        if sanction_max_months and confirmed_no_aggravating(full_text)
        else None
    )
    if per_count:
        statute_checks = _count_checks(sentence, count_statutes or {}, facts, full_text)
    elif _single_part(statute):
        statute_checks.append(
            _imposed_term_check(statute, facts.legal_facts, source_text, art62_limit)
        )
    scale = None
    several_counts = per_count and len(sentence.counts) > 1
    if several_counts and ceiling is not None and ceiling.max_imprisonment_months is not None:
        # The scale of one sanction cannot hold the final term of several offences.
        warnings.append(_statute_warning(statute))
    stage_conflict = per_count and sentence.counts[0].stage_conflict
    if stage_conflict:
        warnings.append(
            "Шкала рекомендации не построена: противоречивые сведения о стадии преступления."
        )
    if sanction_max_months and not several_counts and not stage_conflict:
        limit, limit_norm = art62_limit, "ч. 1 ст. 62" if art62_limit is not None else None
        stage = sentence.counts[0].unfinished if per_count else None
        if stage is not None:
            reduced = reduced_maximum(sanction_max_months, stage)
            exact62 = part1_limit_amount(
                reduced,
                (c.norm for c in facts.mitigating),
                has_aggravating=not confirmed_no_aggravating(full_text),
            )
            limit = float(exact62) if exact62 is not None else reduced
            limit_norm = "ч. 1 ст. 62" if exact62 is not None else ART66_NORMS[stage]
            limit_norm = limit_norm.removesuffix(" УК РФ")
        rec = facts.recommended_months
        cap = limit if limit is not None else sanction_max_months
        scale = SentenceScale(
            sanction_max_months=sanction_max_months,
            limit_months=limit,
            limit_norm=limit_norm,
            recommended_months=rec,
            within_sanction=(rec <= cap) if rec is not None else None,
        )
        comparison = practice.comparison if practice is not None else None
        if comparison is not None and comparison.enough_data and len(practice.query.episodes) <= 1:
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

    extracted = read_court_circumstances("\n\n".join(document_texts or []))
    text_guilt = guilt_from_text("\n\n".join(document_texts or []))
    most_serious = _most_serious_ceiling(sentence, count_statutes or {}) if per_count else None
    legal_checks = statute_checks + build_legal_checks(
        facts.legal_facts,
        source_text,
        statutory_ceiling=most_serious or ceiling,
        extracted_recidivism=extracted.recidivism,
        recidivism_quote=extracted.recidivism_quote,
        extracted_source_text="\n\n".join(document_texts or []),
        text_guilt=text_guilt,
    )
    if per_count and most_serious is None:
        for check in legal_checks:
            if check.norm == "ст. 15 УК РФ":
                check.status, check.value = "insufficient_data", None
                check.explanation = (
                    "Не прочитаны санкции всех эпизодов; самая тяжкая категория не определена."
                )
    cited_guilt = facts.legal_facts.guilt if facts.legal_facts is not None else None
    cited_guilt = cited_guilt or text_guilt
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
        qualification=_with_all_counts(facts.qualification, sentence),
        scale=scale,
        mitigating=facts.mitigating,
        aggravating="; ".join(f"{c.name} — {c.norm}" for c in facts.aggravating)
        or "Подтверждённые отягчающие обстоятельства не извлечены; проверьте текст (ст. 63 УК РФ).",
        personality=facts.personality,
        variants=[_readable_variant(v) for v in facts.variants],
        similar=_precedent_refs(practice)
        if practice and practice.shown
        else _similar_refs(similar_items),
        precedent_source=precedent_source,
        precedents=_precedent_reads(practice) if practice else [],
        practice=_practice_read(practice)
        if practice and len(practice.query.episodes) <= 1
        else None,
        practice_episodes=[_practice_read(r) for r in practice.episodes] if practice else [],
        warnings=warnings,
    )


_VARIANT_KEYS = {
    "final_sentence": "Окончательное",
    "final": "Окончательное",
    "aggregate_crimes": "По совокупности преступлений",
    "aggregate_sentences": "По совокупности приговоров",
    "aggregate_verdicts": "По совокупности приговоров",
    "aggregate": "По совокупности",
    "conditional": "Условно",
    "real": "Реальное",
    "recommended": "Рекомендуемое",
}


def _readable_variant(variant: PunishmentVariant) -> PunishmentVariant:
    """Service keys the model sometimes returns ("offense_1", "final_sentence") become words."""

    def word(text: str) -> str:
        key = text.strip().lower()
        episode = re.fullmatch(r"(?:offen[cs]e|count|episode|crime)_?(\d+)", key)
        if episode:
            return f"Эпизод {episode.group(1)}"
        if key in _VARIANT_KEYS:
            return _VARIANT_KEYS[key]
        for raw, readable in _VARIANT_KEYS.items():
            text = text.replace(raw, readable.lower())
        return text

    updates = {
        key: word(getattr(variant, key)) for key in ("label", "title", "details", "rationale")
    }
    if re.fullmatch(r"[a-z0-9_]+", updates["label"]):
        updates["label"] = updates["title"]
    return variant.model_copy(update=updates)


def _with_all_counts(
    qualification: Qualification | None, sentence: ImposedSentence | None
) -> Qualification | None:
    """The model sometimes names only the first count; every count read from the operative part
    is listed so that the heavier offence is not lost."""
    if sentence is None or not sentence.counts:
        return qualification
    article = qualification.article if qualification is not None else ""
    named = {(r.article, r.part) for r in _article_refs(article)}
    missing = []
    for count in sentence.counts:
        if count.reference is None or not count.qualification:
            continue
        key = (count.reference.article, count.reference.part)
        if key not in named:
            named.add(key)
            missing.append(re.sub(r"\s+", " ", count.qualification).strip())
    if not missing:
        return qualification
    joined = "; ".join(([article] if article else []) + missing)
    return Qualification(article=joined, title=qualification.title if qualification else "")


def _article_refs(text: str) -> list[ArticleReference]:
    refs = []
    for match in re.finditer(
        r"(?:ч\.?\s*(?P<part>\d{1,2})\s*)?ст\.?\s*(?P<article>\d{1,3}(?:\.\d{1,2})?)", text or ""
    ):
        if int(match["article"].split(".")[0]) >= 105:
            refs.append(
                ArticleReference(match["article"], int(match["part"]) if match["part"] else None)
            )
    return refs


def _most_serious_ceiling(
    sentence: ImposedSentence | None, statutes: dict[ArticleReference, StatuteSanctionReading]
) -> SanctionCeiling | None:
    """Ceiling of the count with the longest statutory maximum: ст. 15 categorises the most
    serious offence of the verdict, not the first one the model named."""
    ceilings = [
        _statutory_ceiling(statutes.get(c.reference))
        for c in (sentence.counts if sentence else ())
        if c.reference is not None
    ]
    known = [c for c in ceilings if c is not None]
    if not known or len(known) != len(sentence.counts):
        return None
    return max(
        known,
        key=lambda c: (c.harsher_than_imprisonment, c.max_imprisonment_months or 0),
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
    source_text: str = "",
) -> list[LegalCheck]:
    """Sanction and imposed-punishment checks for every count of the operative part."""
    checks: list[LegalCheck] = []
    seen_sanctions: set[ArticleReference] = set()
    for count in sentence.counts:
        reading = statutes.get(count.reference) if count.reference else None
        if count.stage_conflict:
            checks.append(
                LegalCheck(
                    norm=f"Стадия преступления · {count.qualification}",
                    status="insufficient_data",
                    source=ART66_SOURCE,
                    explanation="Словесная стадия и ссылка на ст. 30 расходятся либо "
                    "стадия не привязана к одному эпизоду; расчёты ст. 66/68 требуют проверки.",
                    evidence=[count.quote],
                )
            )
            continue
        if not _single_part(reading):
            checks.append(_unchecked_count(count))
            continue
        if count.reference not in seen_sanctions:
            seen_sanctions.add(count.reference)
            checks.append(_statute_sanction_check(reading))
        top = most_severe_alternative(reading.sanctions)
        exact_limit = None
        if top and top.max_value and confirmed_no_aggravating(source_text):
            exact_limit = part1_limit_amount(
                reduced_maximum(top.max_value, count.unfinished),
                (c.norm for c in facts.mitigating),
                has_aggravating=bool(facts.aggravating),
            )
        result = check_imposed_punishment(
            count.main,
            reading.sanctions,
            source=reading.provenance.source_url,
            art62_limit_months=None,
            unfinished=count.unfinished,
            art62_limit_amount=exact_limit,
            art64_applied="64"
            in extract_circumstances(count.quote, sentence.final_quote).applied_general,
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
    for count in sentence.counts:
        reading = statutes.get(count.reference) if count.reference else None
        for additional in count.additional:
            result = check_additional(additional, reading.sanctions) if reading else None
            checks.append(
                LegalCheck(
                    norm=f"Дополнительное наказание · {count.qualification}",
                    status=result.status.value if result else "insufficient_data",
                    source=reading.provenance.source_url if reading else "",
                    value=describe_term(additional),
                    evidence=[count.quote],
                    explanation=result.explanation
                    if result
                    else "Санкция дополнительного наказания не найдена.",
                )
            )
    for term, rule, quote in (
        (sentence.intermediate, sentence.intermediate_rule, sentence.intermediate_quote),
        (sentence.final, sentence.aggregation_rule, sentence.final_quote),
    ):
        if term is None:
            continue
        parsed = _aggregation_rule(rule)
        if parsed == "70":
            new = sentence.intermediate or (
                sentence.counts[0].main if len(sentence.counts) == 1 else None
            )
            result = check_article70(term, new, sentence.unserved, sentence.joined)
        elif term.kind is not PunishmentKind.IMPRISONMENT:
            maxima = []
            for count in sentence.counts:
                reading = statutes.get(count.reference)
                options = (
                    [
                        s
                        for s in reading.sanctions
                        if s.kind is count.main.kind
                        and s.unit is count.main.unit
                        and s.role.value == "main"
                    ]
                    if reading
                    else []
                )
                maximum = options[0].max_value if len(options) == 1 else None
                maxima.append(
                    reduced_maximum(maximum, count.unfinished)
                    if maximum and not count.stage_conflict
                    else None
                )
            result = check_other_aggregate(term, [c.main for c in sentence.counts], maxima, parsed)
        else:
            result = check_final_term(
                rule=parsed,
                final_months=term.imprisonment_months,
                count_months=[c.main.imprisonment_months for c in sentence.counts],
                count_max_months=[
                    count_maximum(statutes.get(c.reference), c) for c in sentence.counts
                ],
            )
        label = "Промежуточное" if term is sentence.intermediate else "Окончательное"
        checks.append(
            LegalCheck(
                norm=f"{label} наказание ({rule or 'ст. 69/70 УК РФ'})",
                status=result.status.value,
                value=describe_term(term),
                source=result.source,
                explanation=result.explanation,
                evidence=[q for q in (quote, sentence.unserved_quote, sentence.joined_quote) if q],
            )
        )
        if parsed == "69.5":
            dated = check_prior_chronology(
                [c.offence_date for c in sentence.counts],
                sentence.prior_judgment_date,
                sentence.credited,
            )
            checks.append(
                LegalCheck(
                    norm=dated.norm,
                    status=dated.status.value,
                    source=dated.source,
                    explanation=dated.explanation,
                    evidence=[
                        q
                        for q in [
                            sentence.prior_judgment_quote,
                            sentence.credited_quote,
                            *[c.offence_date_quote for c in sentence.counts],
                        ]
                        if q
                    ],
                )
            )
        if parsed and parsed.startswith("69"):
            categories = []
            for count in sentence.counts:
                reading = statutes.get(count.reference)
                ceiling = _statutory_ceiling(reading)
                guilt = facts.legal_facts.guilt if facts.legal_facts else None
                if guilt is not None and guilt.quote not in source_text:
                    guilt = None
                guilt = guilt or guilt_from_text(count.quote) or guilt_from_text(source_text)
                # Facts of different guilt are never inferred from the article number.
                category = (
                    categorize(Guilt(guilt.value), ceiling)
                    if ceiling and guilt and guilt.value in set(Guilt) and not count.stage_conflict
                    else None
                )
                categories.append(category)
            part_result = check_article69_part(
                int(parsed.split(".")[1]),
                categories,
                [c.unfinished for c in sentence.counts],
                absorption=bool(re.search(r"поглощени", quote, re.I)),
            )
            checks.append(
                LegalCheck(
                    norm=part_result.norm,
                    status=part_result.status.value,
                    source=part_result.source,
                    explanation=part_result.explanation,
                    evidence=[quote],
                )
            )
    for final_extra in sentence.final_additional:
        existing = [extra for c in sentence.counts for extra in c.additional]
        maxima = [
            s.max_value
            for reading in statutes.values()
            for s in reading.sanctions
            if s.role.value == "additional"
            and s.kind is final_extra.kind
            and s.max_value is not None
        ]
        result = check_additional_aggregate(final_extra, existing, max(maxima) if maxima else None)
        checks.append(
            LegalCheck(
                norm=result.norm,
                status=result.status.value,
                source=result.source,
                explanation=result.explanation,
                value=describe_term(final_extra),
                evidence=[sentence.final_quote],
            )
        )
    return checks


def _aggregation_rule(text: str | None) -> str | None:
    """ "ч. 3 ст. 69 УК РФ" -> "69.3"; "ст. 70 УК РФ" -> "70"; anything else -> None."""
    if not text:
        return None
    if re.search(r"ст\.\s*70(?!\d)", text):
        return "70"
    part = re.search(r"ч\.\s*([2345])\s+ст\.\s*69(?!\d)", text)
    return f"69.{part.group(1)}" if part else None


def count_maximum(reading: StatuteSanctionReading | None, count: CountSentence) -> float | None:
    """Imprisonment maximum that binds the court for the count: the sanction's maximum, reduced
    under ст. 66 for an unfinished offence. None when the sanction is not read."""
    if not _single_part(reading) or count.stage_conflict:
        return None
    ceiling = _statutory_ceiling(reading)
    if ceiling is None or not ceiling.max_imprisonment_months:
        return None
    return reduced_maximum(ceiling.max_imprisonment_months, count.unfinished)


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
        intermediate=describe_term(sentence.intermediate) if sentence.intermediate else None,
        intermediate_rule=sentence.intermediate_rule,
        unserved=describe_term(sentence.unserved) if sentence.unserved else None,
        joined=describe_term(sentence.joined) if sentence.joined else None,
        final_additional=[describe_term(t) for t in sentence.final_additional],
        prior_judgment_date=sentence.prior_judgment_date.isoformat()
        if sentence.prior_judgment_date
        else None,
        credited=describe_term(sentence.credited) if sentence.credited else None,
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
        t_llm = time.monotonic()
        logger.info(
            "[CASE-ANALYZER] Calling LLM extract_facts (attempt %d/2, prompt_chars=%d)...",
            attempt,
            len(system) + len(user),
        )
        data = await llm.complete_json(system, user)
        llm_sec = time.monotonic() - t_llm
        logger.info("[CASE-ANALYZER] LLM returned response in %.2fs", llm_sec)
        try:
            facts = LlmCaseFacts.model_validate(data)
            logger.info(
                "[CASE-ANALYZER] Facts validated in %.2fs (qualification=%s)",
                time.monotonic() - t_llm,
                facts.qualification.article if facts.qualification else None,
            )
            return facts
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "LLM output failed validation (attempt %s): %s", attempt, exc.error_count()
            )
    raise LLMError("Ответ модели не соответствует схеме анализа") from last_error
