# Domain Layer — ст. 73 УК РФ «Условное осуждение»: допустимость и испытательный срок.
# ч. 1: условно могут быть назначены исправительные работы, ограничение по военной службе,
# содержание в дисциплинарной воинской части и лишение свободы на срок до восьми лет;
# не назначается в случаях пп. «а», «а.1», «б», «в» ч. 1 (п. «в» — опасный или особо опасный
# рецидив). ч. 3: испытательный срок — от 6 месяцев до 3 лет при лишении свободы до одного года
# или более мягком наказании, от 6 месяцев до 5 лет при лишении свободы свыше одного года.
# Пункты «а», «а.1», «б» зависят от состава и истории осуждённого: их устанавливает вызывающий
# (other_exclusions); машинно здесь проверяются вид и срок наказания, п. «в» и ч. 3.

from collections.abc import Iterable
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
NORM = "Условное осуждение: ч. 1, 3 ст. 73 УК РФ"
SOURCE = (
    "УК РФ ст. 73, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "1fc6797cfe603f5b327aa4ea29644309db22717d/ (УК РФ ред. от 04.08.2026, сверено 28.10.2026)"
)
MAX_CONDITIONAL_IMPRISONMENT_MONTHS = 96
PROBATION_MIN_MONTHS = 6
PROBATION_MAX_SHORT_MONTHS = 36  # лишение свободы до одного года или более мягкое наказание
PROBATION_MAX_LONG_MONTHS = 60  # лишение свободы свыше одного года
EXCLUSION_ITEMS = {"а", "а.1", "б"}


class ConditionalKind(StrEnum):
    IMPRISONMENT = "imprisonment"
    CORRECTIONAL_LABOUR = "correctional_labour"
    MILITARY_RESTRICTION = "military_restriction"
    DISCIPLINARY_UNIT = "disciplinary_unit"
    OTHER = "other"  # любое иное наказание: условно не назначается


def probation_bounds(kind: ConditionalKind, months: int | None) -> tuple[int, int] | None:
    """Границы испытательного срока (мес.) по ч. 3 ст. 73; None — срок не известен."""
    if kind is ConditionalKind.IMPRISONMENT:
        if months is None:
            return None
        upper = PROBATION_MAX_LONG_MONTHS if months > 12 else PROBATION_MAX_SHORT_MONTHS
        return PROBATION_MIN_MONTHS, upper
    return PROBATION_MIN_MONTHS, PROBATION_MAX_SHORT_MONTHS


def check_conditional_sentence(
    *,
    conditional: bool,
    kind: ConditionalKind,
    imprisonment_months: int | None,
    probation_months: int | None,
    recidivism: Recidivism,
    other_exclusions: Iterable[str] = (),
) -> CheckResult:
    """Кандидатная проверка условного осуждения по ч. 1 и 3 ст. 73 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW)

    if not conditional:
        return result(CheckStatus.OK, "Наказание назначено реально — ст. 73 УК РФ не применялась.")

    violations: list[str] = []
    gaps: list[str] = []
    if kind is ConditionalKind.OTHER:
        violations.append("этот вид наказания не может быть назначен условно (ч. 1 ст. 73)")
    elif kind is ConditionalKind.IMPRISONMENT:
        if imprisonment_months is None:
            gaps.append("срок лишения свободы не определён")
        elif imprisonment_months > MAX_CONDITIONAL_IMPRISONMENT_MONTHS:
            violations.append(
                f"лишение свободы {imprisonment_months} мес. — условно только до 8 лет "
                "(ч. 1 ст. 73)"
            )

    if recidivism in (Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS):
        violations.append("при опасном или особо опасном рецидиве (п. «в» ч. 1 ст. 73)")
    elif recidivism is Recidivism.UNKNOWN:
        gaps.append("вид рецидива не установлен (п. «в» ч. 1 ст. 73)")

    excluded = sorted(set(other_exclusions) & EXCLUSION_ITEMS)
    for item in excluded:
        violations.append(f"случай п. «{item}» ч. 1 ст. 73")

    bounds = probation_bounds(kind, imprisonment_months)
    if probation_months is None:
        gaps.append("испытательный срок не определён")
    elif bounds is not None:
        low, high = bounds
        if not low <= probation_months <= high:
            violations.append(
                f"испытательный срок {probation_months} мес. вне пределов {low}–{high} мес. "
                "(ч. 3 ст. 73)"
            )

    if violations:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Условное осуждение: " + "; ".join(violations) + ".",
        )
    if gaps:
        return result(CheckStatus.INSUFFICIENT_DATA, "Не проверено: " + "; ".join(gaps) + ".")
    return result(
        CheckStatus.OK,
        "Условное осуждение допустимо по виду и сроку наказания и рецидиву; испытательный срок в "
        "пределах ч. 3 ст. 73. Пункты «а», «а.1», «б» ч. 1 проверьте по составу и истории.",
    )
