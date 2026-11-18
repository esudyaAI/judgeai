"""Checks of the imposed sentence that build on the recidivism found under ст. 18 (T13, step 1).

ч. 2–3 ст. 68 per count, against the sanction from the imported УК РФ text, and ст. 73 for a
conditional sentence, ч. 1 ст. 58 when the operative part names a correctional institution
(sex and previous imprisonment are read from the text by regex_facts, category and guilt come
from the confirmed ст. 15 check). The rules live in legal_core; this module only maps the read
sentence and the earlier checks to their inputs.
"""

import re
from collections.abc import Iterable
from fractions import Fraction

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
)
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art66 import NORMS as ART66_NORMS
from legal_core.rules.art66 import reduced_maximum
from legal_core.rules.art68 import check_recidivism_amount
from legal_core.rules.art73 import ConditionalKind, check_conditional_sentence
from legal_core.rules.imposed_term import most_severe_alternative

from src.domain.prepared_sentencing import (
    PreparedRegimeInputs,
    PreparedSentencingInputs,
    evaluate_regime_inputs,
)
from src.infrastructure.circumstance_extractor import extract_circumstances
from src.schemas.analysis import Circumstance, LegalCheck
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.regime_facts import prepare_regime_inputs

ART15_NORM = "ст. 15 УК РФ"
ART18_NORM = "ст. 18 УК РФ"
_ART61 = re.compile(r"ст\.?\s*61(?![\d.])", re.IGNORECASE)
_ESTABLISHED = {Recidivism.SIMPLE, Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS}
_HARSHER_THAN_IMPRISONMENT = {PunishmentKind.LIFE_IMPRISONMENT, PunishmentKind.DEATH_PENALTY}
_CONDITIONAL_KINDS = {
    PunishmentKind.IMPRISONMENT: ConditionalKind.IMPRISONMENT,
    PunishmentKind.CORRECTIONAL_WORKS: ConditionalKind.CORRECTIONAL_LABOUR,
    PunishmentKind.MILITARY_SERVICE_RESTRICTION: ConditionalKind.MILITARY_RESTRICTION,
    PunishmentKind.DISCIPLINARY_MILITARY_UNIT: ConditionalKind.DISCIPLINARY_UNIT,
}


def recidivism_of(checks: Iterable[LegalCheck]) -> Recidivism:
    """Calculated recidivism or a nonconflicting quoted court finding; otherwise UNKNOWN."""
    for check in checks:
        if check.norm == ART18_NORM and check.recidivism_input and check.evidence:
            return Recidivism(check.recidivism_input)
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
        rule_key=result.rule_key,  # T15.18: the finding opens its basis in the reference
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
    *,
    art64: bool | None = None,
) -> LegalCheck:
    if count.stage_conflict:
        return LegalCheck(
            norm=f"ст. 66/68 УК РФ · {count.qualification}",
            status="insufficient_data",
            source="ст. 66, 68 УК РФ",
            explanation="Противоречивые сведения о стадии эпизода.",
            evidence=[count.quote],
        )
    top = most_severe_alternative(reading.sanctions) if reading is not None else None
    maximum = reduced_maximum(top.max_value, count.unfinished) if top and top.max_value else None
    if top and top.kind in _HARSHER_THAN_IMPRISONMENT:
        return LegalCheck(
            norm=f"ст. 68 УК РФ · {count.qualification}",
            status="insufficient_data",
            source="ст. 68 УК РФ",
            explanation="Санкция содержит пожизненное лишение свободы или "
            "смертную казнь; максимум трети не определён.",
            evidence=[count.quote],
        )
    amount = count.main.amount
    if top and count.main.unit is MeasureUnit.DAYS and top.unit is MeasureUnit.MONTHS:
        amount = Fraction(str(amount)) / 30 if amount else None
    compatible = bool(
        top
        and (
            count.main.unit is top.unit
            or (count.main.unit is MeasureUnit.DAYS and top.unit is MeasureUnit.MONTHS)
        )
    )
    result = check_recidivism_amount(
        recidivism=recidivism,
        amount=amount if compatible else None,
        maximum=maximum,
        most_severe_kind=top is None or count.main.kind is top.kind,
        mitigating=art61,
        art64=("64" in extract_circumstances(count.quote, final_quote).applied_general)
        if art64 is None
        else art64,
        unit_name={
            MeasureUnit.MONTHS: "мес.",
            MeasureUnit.HOURS: "ч.",
            MeasureUnit.RUBLES: "руб.",
        }.get(top.unit if top else None, "ед."),
    )
    source = reading.provenance.source_url if reading is not None else ""
    check = _legal_check(result, count.qualification, _months(count.main), [count.quote])
    if count.unfinished is not None and maximum is not None:
        check.explanation += (
            f" Треть взята от максимума, сниженного по {ART66_NORMS[count.unfinished]}: "
            f"{maximum} мес."
        )
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
    prepared: PreparedRegimeInputs | None = None,
) -> LegalCheck | None:
    inputs = prepared if prepared is not None else prepare_regime_inputs(document_text)
    result = evaluate_regime_inputs(inputs, recidivism, category, guilt)
    if result is None:
        return None
    return _legal_check(
        result,
        "",
        inputs.imposed.quote,
        [inputs.imposed.quote, inputs.male.quote, inputs.served_before.quote],
    )


def build_sentence_checks(
    sentence: ImposedSentence | None,
    statutes: dict[ArticleReference, StatuteSanctionReading],
    earlier_checks: list[LegalCheck],
    mitigating: list[Circumstance],
    *,
    document_text: str = "",
    guilt: str | None = None,
    prepared: PreparedSentencingInputs | None = None,
) -> list[LegalCheck]:
    """ст. 68 for every count when recidivism is established; ст. 73 when the sentence is
    conditional. Nothing is added for a draft without an operative part."""
    if prepared is not None and prepared.sentence != sentence:
        raise ValueError("Prepared sentencing inputs do not match the sentence")
    if sentence is None or sentence.is_empty:
        return []
    recidivism = recidivism_of(earlier_checks)
    checks: list[LegalCheck] = []
    unknown = set(prepared.unknown_fields) if prepared is not None else set()
    if recidivism in _ESTABLISHED:
        art61 = any(_ART61.search(item.norm or "") for item in mitigating)
        for index, count in enumerate(sentence.counts):
            if f"count/{index}/main" in unknown:
                checks.append(
                    LegalCheck(
                        norm=f"ст. 68 УК РФ · {count.qualification}",
                        status="insufficient_data",
                        source="",
                        explanation="Основное наказание оставлено неизвестным пользователем.",
                    )
                )
                continue
            reading = statutes.get(count.reference) if count.reference else None
            checks.append(
                _art68_count(
                    count,
                    reading,
                    recidivism,
                    art61,
                    sentence.final_quote,
                    art64=prepared.art64_by_count[index].value is True
                    if prepared is not None
                    else None,
                )
            )
    if "conditional" in unknown:
        checks.append(
            LegalCheck(
                norm="ст. 73 / ст. 58 УК РФ",
                status="insufficient_data",
                source="",
                explanation=(
                    "Условность осуждения оставлена неизвестной пользователем; "
                    "проверки условного осуждения и вида учреждения не выполнены."
                ),
            )
        )
    elif sentence.conditional:
        if "final" in unknown or (sentence.final is None and "count/0/main" in unknown):
            checks.append(
                LegalCheck(
                    norm="ст. 73 УК РФ",
                    status="insufficient_data",
                    source="",
                    explanation="Назначенное наказание оставлено неизвестным пользователем.",
                )
            )
        else:
            checks.append(_art73(sentence, recidivism))
    else:
        category = _category_of(earlier_checks)
        known_guilt = Guilt(guilt) if category is not None and guilt in set(Guilt) else None
        regime = _art58(
            document_text,
            recidivism,
            category,
            known_guilt,
            prepared.regime if prepared is not None else None,
        )
        if regime is not None:
            checks.append(regime)
    for earlier in earlier_checks:
        if earlier.norm == ART18_NORM and earlier.recidivism_input:
            for check in checks:
                check.evidence = list(dict.fromkeys([*check.evidence, *earlier.evidence]))
                check.explanation += (
                    " Вид рецидива взят из цитированного указания суда; требуется сверка."
                )
    return checks
