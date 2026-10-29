# Domain Layer — ч. 2 и 3 ст. 68 УК РФ «Назначение наказания при рецидиве преступлений».
# ч. 2: the term under any kind of recidivism cannot be less than one third of the maximum term
# of the most severe punishment for the offence, within the sanction of the article.
# ч. 3: with mitigating circumstances under ст. 61 the term may be below one third (within the
# sanction); with exceptional circumstances under ст. 64 a milder punishment may be imposed.
# Пленум ВС РФ № 58 от 22.12.2015: п. 47 — a milder kind than the most severe one only under
# ст. 64; п. 48 — not below the minimum of the sanction (checked by imposed_term, not here);
# п. 49 — for an unfinished offence one third is taken of the maximum reduced under ст. 66.
# TODO(T4/T23): ст. 66 (unfinished offence) is not modelled — the caller passes the maximum it
# applies; ч. 1 (circumstances the court must weigh) is not machine-checkable.

import math

from legal_core.checks import CheckResult, CheckStatus
from legal_core.rules.art18 import Recidivism

NEEDS_LEGAL_REVIEW = True
NORM = "Срок наказания при рецидиве: ч. 2, 3 ст. 68 УК РФ"
SOURCE = (
    "УК РФ ст. 68 (ред. Федерального закона от 08.12.2003 N 162-ФЗ), текст по "
    "https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "e2bec0404d1dac2c1b416808f5dd491e7ba46799/ (УК РФ ред. от 04.08.2026, сверено 28.10.2026); "
    "Пленум ВС РФ от 22.12.2015 N 58, пп. 47–49"
)


def part2_minimum_months(sanction_max_months: float) -> int:
    """One third of the maximum, in whole months, rounded up.

    Rounded up: a whole-month term equal to the rounded-down value would already be below one
    third of the maximum (e.g. 17 of 52 months).
    """
    if sanction_max_months <= 0:
        raise ValueError("sanction maximum must be positive")
    return math.ceil(sanction_max_months / 3)


def check_recidivism_term(
    *,
    recidivism: Recidivism,
    imposed_months: int | None,
    most_severe_max_months: float | None,
    imposed_most_severe_kind: bool,
    art61_mitigating_established: bool,
    art64_applied: bool,
) -> CheckResult:
    """Candidate check of the imposed term against ч. 2–3 ст. 68 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW)

    if recidivism is Recidivism.NONE:
        return result(CheckStatus.OK, "Рецидива нет — ст. 68 УК РФ не применяется.")
    if recidivism is Recidivism.UNKNOWN:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Вид рецидива не установлен — ограничение ч. 2 ст. 68 УК РФ не проверено.",
        )
    if art64_applied:
        return result(
            CheckStatus.OK,
            "Применена ст. 64 УК РФ — ограничения ч. 2 ст. 68 не действуют.",
        )
    if not imposed_most_severe_kind:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "При рецидиве назначен не наиболее строгий вид наказания без ссылки на ст. 64 УК РФ "
            "(Пленум ВС РФ N 58, п. 47).",
        )
    if (
        imposed_months is None
        or imposed_months < 0
        or most_severe_max_months is None
        or most_severe_max_months <= 0
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Срок наказания или максимум санкции не определены.",
        )

    minimum = part2_minimum_months(most_severe_max_months)
    if imposed_months >= minimum:
        return result(
            CheckStatus.OK,
            f"Назначено {imposed_months} мес. — не менее трети максимума "
            f"({minimum} из {most_severe_max_months} мес.).",
        )
    if art61_mitigating_established:
        return result(
            CheckStatus.OK,
            f"Назначено {imposed_months} мес. — менее трети максимума ({minimum} мес.) при "
            "смягчающих ст. 61 УК РФ: допускается ч. 3 ст. 68, проверьте мотивировку.",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"Назначено {imposed_months} мес. — менее трети максимума ({minimum} из "
        f"{most_severe_max_months} мес.) без смягчающих ст. 61 и без ст. 64 УК РФ.",
    )


def check_recidivism_amount(
    *,
    recidivism: Recidivism,
    amount: float | None,
    maximum: float | None,
    most_severe_kind: bool,
    mitigating: bool,
    art64: bool,
    unit_name: str,
) -> CheckResult:
    """Exact one-third boundary in the actual unit (months, hours or rubles), T37.

    No premature ceil/floor: days under ст.72 can express fractions of a month.
    Source and review requirement are the same as check_recidivism_term.
    """
    from fractions import Fraction

    def result(status, why):
        return CheckResult(NORM, status, why, SOURCE, True)

    if recidivism is Recidivism.UNKNOWN:
        return result(CheckStatus.INSUFFICIENT_DATA, "Вид рецидива не установлен.")
    if recidivism is Recidivism.NONE or art64:
        return result(
            CheckStatus.OK, "Ограничение трети не применяется: нет рецидива либо применена ст. 64."
        )
    if not most_severe_kind:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Назначен не наиболее строгий вид наказания без ст. 64 (п. 47 ППВС №58).",
        )
    if amount is None or maximum is None or amount <= 0 or maximum <= 0:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Размер наказания или максимум наиболее строгого вида не определён.",
        )
    third = Fraction(str(maximum)) / 3
    if Fraction(str(amount)) >= third:
        return result(
            CheckStatus.OK,
            f"Назначено {amount:g} {unit_name}, не менее трети ({third} {unit_name}).",
        )
    if mitigating:
        return result(
            CheckStatus.OK,
            f"Ниже трети ({third} {unit_name}) при смягчающих ст. 61: "
            "проверьте мотивировку ч. 3 ст. 68.",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"Назначено {amount:g} {unit_name} ниже трети ({third} {unit_name}) без ст. 61/64.",
    )
