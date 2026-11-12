"""Conservative bridge from quoted model extractions to deterministic domain rules.

Exact quote matching establishes provenance, not semantic correctness or law edition.
Every candidate therefore requires human review; no inference from absent history.
"""

import re

from legal_core.entities import Guilt, SanctionCeiling
from legal_core.precedents import Recidivism
from legal_core.rules.art15 import RULE_KEY as ART15_RULE
from legal_core.rules.art15 import SOURCE as ART15_SOURCE
from legal_core.rules.art18 import RULE_KEY as ART18_RULE
from legal_core.rules.art18 import SOURCE as ART18_SOURCE

from src.domain.prepared_legal import (
    PRIOR_FIELD_KINDS,
    PreparedFact,
    PreparedLegalInputs,
    evaluate_legal_inputs,
)
from src.schemas.analysis import CitedFact, LegalCheck, LegalFacts

_INTENT = re.compile(r"[^.\n]{0,160}\bумышленн\w*[^.\n]{0,160}", re.IGNORECASE)
_NEGLIGENCE = re.compile(r"[^.\n]{0,160}\bпо\s+неосторожности[^.\n]{0,160}", re.IGNORECASE)


def guilt_from_text(text: str) -> CitedFact | None:
    """Form of guilt quoted from the verdict itself when the model cited none; nothing when the
    text names both forms (several offences may differ) or neither."""
    intent, negligence = _INTENT.search(text or ""), _NEGLIGENCE.search(text or "")
    if bool(intent) == bool(negligence):
        return None
    match = intent or negligence
    value = Guilt.INTENTIONAL if intent else Guilt.NEGLIGENT
    return CitedFact(value=value.value, quote=match.group(0).strip())


def _value(fact: CitedFact | None, text: str, kind: type):
    if fact is None or fact.quote not in text or type(fact.value) is not kind:
        raise ValueError("missing, unsupported or mistyped fact")
    return fact.value


def _prepared(fact, text, kind):
    try:
        return PreparedFact(_value(fact, text, kind), fact.quote)
    except ValueError:
        return PreparedFact()


def prepare_legal_inputs(
    facts: LegalFacts | None,
    source_text: str,
    *,
    extracted_recidivism: Recidivism | None = None,
    recidivism_quote: str = "",
    extracted_source_text: str | None = None,
    text_guilt: CitedFact | None = None,
) -> PreparedLegalInputs:
    full_text = extracted_source_text if extracted_source_text is not None else source_text
    model = facts.guilt if facts is not None else None
    model_guilt = _prepared(model, source_text, str)
    use_text = model is None and text_guilt is not None
    selected = _prepared(text_guilt, full_text, str) if use_text else model_guilt
    priors = (
        tuple(
            tuple(
                (name, _prepared(row.get(name), source_text, kind))
                for name, kind in PRIOR_FIELD_KINDS
            )
            for row in facts.prior_convictions
        )
        if facts is not None
        else ()
    )
    stated = extracted_recidivism if recidivism_quote and recidivism_quote in full_text else None
    return PreparedLegalInputs(
        model_guilt=model_guilt,
        category_guilt=selected,
        category_uses_text=use_text,
        category=_prepared(facts.category if facts else None, source_text, str),
        real_imprisonment=_prepared(facts.real_imprisonment if facts else None, source_text, bool),
        history_complete=_prepared(facts.history_complete if facts else None, source_text, bool),
        prior_convictions=priors,
        stated_recidivism=stated,
        stated_quote=recidivism_quote if stated is not None else "",
    )


def build_legal_checks(
    facts: LegalFacts | None,
    source_text: str,
    statutory_ceiling: SanctionCeiling | None = None,
    extracted_recidivism: Recidivism | None = None,
    recidivism_quote: str = "",
    extracted_source_text: str | None = None,
    text_guilt: CitedFact | None = None,
    *,
    prepared: PreparedLegalInputs | None = None,
) -> list[LegalCheck]:
    inputs = (
        prepared
        if prepared is not None
        else prepare_legal_inputs(
            facts,
            source_text,
            extracted_recidivism=extracted_recidivism,
            recidivism_quote=recidivism_quote,
            extracted_source_text=extracted_source_text,
            text_guilt=text_guilt,
        )
    )
    evaluated = evaluate_legal_inputs(inputs, statutory_ceiling)
    checks = [
        LegalCheck(
            norm=norm,
            source=source,
            status="insufficient_data",
            explanation="Недостаточно подтверждённых фактов; правовой вывод не сделан.",
            rule_key=rule_key,
        )
        for norm, source, rule_key in [
            ("ст. 15 УК РФ", ART15_SOURCE, ART15_RULE),
            ("ст. 18 УК РФ", ART18_SOURCE, ART18_RULE),
        ]
    ]
    category, recidivism = checks
    if evaluated.category is not None:
        category.status, category.value = "ok", evaluated.category
        category.evidence = list(evaluated.category_evidence)
        category.explanation = (
            "Предварительная категория по процитированным данным. Проверьте санкцию "
            "статьи, дату преступления и применимую редакцию закона."
        )
        if inputs.category_uses_text:
            category.explanation += " Форма вины взята из текста приговора."
    if evaluated.recidivism is not None:
        recidivism.status, recidivism.value = "ok", evaluated.recidivism
        recidivism.explanation = (
            "Предварительный вид рецидива. Проверьте полноту сведений о судимостях, "
            "отдельность приговоров, их действительность и все даты на момент преступления."
        )
    recidivism.evidence = list(evaluated.recidivism_evidence)
    stated = evaluated.stated_recidivism
    if stated is not None:
        label = {
            Recidivism.NONE: "отсутствует",
            Recidivism.SIMPLE: "простой",
            Recidivism.DANGEROUS: "опасный",
            Recidivism.ESPECIALLY_DANGEROUS: "особо опасный",
        }[stated]
        if evaluated.recidivism_conflict:
            recidivism.status = "insufficient_data"
            recidivism.explanation += (
                " Расчёт расходится с указанием рецидива в тексте; нужна сверка."
            )
        elif evaluated.recidivism is None:
            recidivism.explanation = (
                "В тексте указан вид рецидива. Это извлечённый факт, а не проверка его "
                "правильности по ст. 18; для расчёта недостаточно сведений о судимостях."
            )
        recidivism.recidivism_input = evaluated.recidivism_input
        if evaluated.recidivism is None:
            recidivism.value = f"В тексте: {label}"
        recidivism.explanation += f" В тексте: {label}."
    return checks
