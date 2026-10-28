"""Checks of the imposed sentence that build on the recidivism found under ст. 18 (T13, step 1).

ч. 2–3 ст. 68 per count, against the sanction from the imported УК РФ text, and ст. 73 for a
conditional sentence, ч. 1 ст. 58 when the operative part names a correctional institution
(sex and previous imprisonment are read from the text by regex_facts, category and guilt come
from the confirmed ст. 15 check). The rules live in legal_core; this module only maps the read
sentence and the earlier checks to their inputs.
"""

import re
from collections.abc import Iterable

from legal_core.checks import CheckResult
from legal_core.entities import (
    ArticleReference,
    Category,
    CountSentence,
    Guilt,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
)
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import check_regime
from legal_core.rules.art68 import check_recidivism_term
from legal_core.rules.art73 import ConditionalKind, check_conditional_sentence
from legal_core.rules.imposed_term import main_imprisonment

from src.schemas.analysis import Circumstance, LegalCheck
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.regime_facts import read_male, read_regime, read_served_before

ART15_NORM = "ст. 15 УК РФ"
ART18_NORM = "ст. 18 УК РФ"
_ART61 = re.compile(r"ст\.?\s*61(?![\d.])", re.IGNORECASE)
_ART64 = re.compile(r"ст\.?\s*64(?![\d.])", re.IGNORECASE)
_ESTABLISHED = {Recidivism.SIMPLE, Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS}
_HARSHER_THAN_IMPRISONMENT = {PunishmentKind.LIFE_IMPRISONMENT, PunishmentKind.DEATH_PENALTY}
_CONDITIONAL_KINDS = {
    PunishmentKind.IMPRISONMENT: ConditionalKind.IMPRISONMENT,
    PunishmentKind.CORRECTIONAL_WORKS: ConditionalKind.CORRECTIONAL_LABOUR,
    PunishmentKind.MILITARY_SERVICE_RESTRICTION: ConditionalKind.MILITARY_RESTRICTION,
    PunishmentKind.DISCIPLINARY_MILITARY_UNIT: ConditionalKind.DISCIPLINARY_UNIT,
}


def recidivism_of(checks: Iterable[LegalCheck]) -> Recidivism:
    """Kind of recidivism from a confirmed ст. 18 check; anything else is UNKNOWN."""
    for check in checks:
        if check.norm == ART18_NORM and check.status == "ok" and check.value:
            try:
                return Recidivism(check.value)
            except ValueError:
                return Recidivism.UNKNOWN
    return Recidivism.UNKNOWN


def _legal_check(result: CheckResult, label: str, value: str | None, evidence) -> LegalCheck:
    return LegalCheck(
        norm=f"{result.norm} · {label}" if label else result.norm,
        status=result.status.value,
        explanation=result.explanation,
        source=result.source,
        value=value,
        evidence=[quote for quote in evidence if quote],
        needs_legal_review=result.needs_legal_review,
    )


def _months(term: PunishmentTerm | None) -> str | None:
    months = term.imprisonment_months if term is not None else None
    return f"{months} мес. лишения свободы" if months is not None else None


def _art68_count(
    count: CountSentence,
    reading: StatuteSanctionReading | None,
    recidivism: Recidivism,
    art61: bool,
    final_quote: str,
) -> LegalCheck:
    maximum = None
    most_severe_kind = True  # unknown sanction: let the rule report missing data, not the kind
    if reading is not None:
        main_kinds = {s.kind for s in reading.sanctions if s.role is SanctionRole.MAIN}
        top = main_imprisonment(reading.sanctions)
        if (
            top is not None
            and top.unit is MeasureUnit.MONTHS
            and top.max_value
            and not main_kinds & _HARSHER_THAN_IMPRISONMENT
        ):
            maximum = int(top.max_value)
            most_severe_kind = count.main.kind is PunishmentKind.IMPRISONMENT
    result = check_recidivism_term(
        recidivism=recidivism,
        imposed_months=count.main.imprisonment_months,
        most_severe_max_months=maximum,
        imposed_most_severe_kind=most_severe_kind,
        art61_mitigating_established=art61,
        art64_applied=bool(_ART64.search(count.quote) or _ART64.search(final_quote)),
    )
    source = reading.provenance.source_url if reading is not None else ""
    check = _legal_check(result, count.qualification, _months(count.main), [count.quote])
    if source:
        check.source = f"{check.source}; санкция: {source}"
    return check


def _art73(sentence: ImposedSentence, recidivism: Recidivism) -> LegalCheck:
    term = sentence.final
    if term is None and len(sentence.counts) == 1:
        term = sentence.counts[0].main
    kind = _CONDITIONAL_KINDS.get(term.kind, ConditionalKind.OTHER) if term else None
    result = check_conditional_sentence(
        conditional=True,
        kind=kind or ConditionalKind.IMPRISONMENT,
        imprisonment_months=term.imprisonment_months if term else None,
        probation_months=sentence.probation_months,
        recidivism=recidivism,
    )
    value = _months(term)
    if sentence.probation_months is not None:
        probation = f"испытательный срок {sentence.probation_months} мес."
        value = f"{value}, {probation}" if value else probation
    return _legal_check(result, "", value, [sentence.final_quote])


def _category_of(checks: Iterable[LegalCheck]) -> Category | None:
    for check in checks:
        if check.norm == ART15_NORM and check.status == "ok" and check.value:
            try:
                return Category[check.value.upper()]
            except KeyError:
                return None
    return None


def _art58(
    document_text: str,
    recidivism: Recidivism,
    category: Category | None,
    guilt: Guilt | None,
) -> LegalCheck | None:
    imposed, regime_quote = read_regime(document_text)
    if imposed is None:
        return None
    male, sex_quote = read_male(document_text)
    served, served_quote = read_served_before(document_text)
    result = check_regime(
        imposed=imposed,
        guilt=guilt,
        category=category,
        male=male,
        recidivism=recidivism,
        served_imprisonment_before=served,
    )
    return _legal_check(result, "", regime_quote, [regime_quote, sex_quote, served_quote])


def build_sentence_checks(
    sentence: ImposedSentence | None,
    statutes: dict[ArticleReference, StatuteSanctionReading],
    earlier_checks: list[LegalCheck],
    mitigating: list[Circumstance],
    *,
    document_text: str = "",
    guilt: str | None = None,
) -> list[LegalCheck]:
    """ст. 68 for every count when recidivism is established; ст. 73 when the sentence is
    conditional. Nothing is added for a draft without an operative part."""
    if sentence is None or sentence.is_empty:
        return []
    recidivism = recidivism_of(earlier_checks)
    checks: list[LegalCheck] = []
    if recidivism in _ESTABLISHED:
        art61 = any(_ART61.search(item.norm or "") for item in mitigating)
        for count in sentence.counts:
            reading = statutes.get(count.reference) if count.reference else None
            checks.append(_art68_count(count, reading, recidivism, art61, sentence.final_quote))
    if sentence.conditional:
        checks.append(_art73(sentence, recidivism))
    else:
        category = _category_of(earlier_checks)
        known_guilt = Guilt(guilt) if category is not None and guilt in set(Guilt) else None
        regime = _art58(document_text, recidivism, category, known_guilt)
        if regime is not None:
            checks.append(regime)
    return checks
