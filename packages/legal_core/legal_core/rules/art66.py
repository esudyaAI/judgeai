# Domain Layer — ч. 2–4 ст. 66 УК РФ «Назначение наказания за неоконченное преступление».
# ч. 2: the term or amount for preparation cannot exceed one half of the maximum term or amount
# of the most severe punishment the Special Part article provides for the completed offence.
# ч. 3: for an attempt — three quarters of the same maximum.
# ч. 4: death penalty and life imprisonment are not imposed for preparation or attempt.
# Пленум ВС РФ № 58 от 22.12.2015, п. 49: with recidivism one third under ч. 2 ст. 68 is taken of
# the maximum already reduced under ст. 66; the same reduced maximum bounds ч. 1 ст. 62.
# Two entry points: `reduced_maximum` (stage as `entities.Unfinished`, used by the analysis) and
# `check_unfinished_offence_term` (catalog rule `art66.unfinished_offence`, stage as
# `OffenceStage`, used by the cumulation rules of ст. 69).
# TODO(T13/T23): ч. 1 (circumstances that prevented completion) is not machine-checkable; the
# stage (ст. 30 УК РФ) comes from the verdict; limits for milder kinds than the most severe one
# and sanctions whose most severe kind is life imprisonment / death penalty are not modelled.
import math
from enum import StrEnum
from fractions import Fraction

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Unfinished

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art66.unfinished_offence"
NORM = "Наказание за неоконченное преступление: ч. 2–4 ст. 66 УК РФ"
SOURCE = (
    "УК РФ ст. 66, текст по https://www.consultant.ru/document/cons_doc_LAW_10699/"
    "af35694e0d25cea91a63d8e3e3859aa42703a8d7/ (УК РФ ред. от 04.08.2026, сверено 08.11.2026); "
    "Пленум ВС РФ от 22.12.2015 N 58, п. 49"
)

_SHARE = {Unfinished.PREPARATION: Fraction(1, 2), Unfinished.ATTEMPT: Fraction(3, 4)}
NORMS = {Unfinished.PREPARATION: "ч. 2 ст. 66 УК РФ", Unfinished.ATTEMPT: "ч. 3 ст. 66 УК РФ"}
SHARE_WORDS = {Unfinished.PREPARATION: "половина", Unfinished.ATTEMPT: "три четверти"}


def reduced_maximum(maximum: float, stage: Unfinished | None) -> float:
    """The maximum that binds the court for this stage; the full maximum for a completed offence."""
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    if stage is None:
        return maximum
    value = Fraction(maximum).limit_denominator() * _SHARE[stage]
    return int(value) if value.denominator == 1 else float(value)


class OffenceStage(StrEnum):
    """Stage of the offence (ст. 29–30 УК РФ) as established in the verdict."""

    COMPLETED = "completed"
    ATTEMPT = "attempt"  # ч. 3 ст. 30
    PREPARATION = "preparation"  # ч. 1 ст. 30
    UNKNOWN = "unknown"


_FRACTION = {OffenceStage.PREPARATION: (1, 2), OffenceStage.ATTEMPT: (3, 4)}
_PART = {OffenceStage.PREPARATION: "ч. 2 ст. 66", OffenceStage.ATTEMPT: "ч. 3 ст. 66"}
_SHARE_GENITIVE = {OffenceStage.PREPARATION: "половины", OffenceStage.ATTEMPT: "трёх четвертей"}


def unfinished_maximum(sanction_max_months: int, stage: OffenceStage) -> int | None:
    """Maximum term in whole months for the stage, or None when the stage is unknown.

    Rounded down: rounding up could allow a term above the statutory share (15 / 2 = 7.5 —
    8 months already exceed one half).
    """
    if sanction_max_months <= 0:
        raise ValueError("sanction maximum must be positive")
    if stage is OffenceStage.UNKNOWN:
        return None
    if stage is OffenceStage.COMPLETED:
        return sanction_max_months
    numerator, denominator = _FRACTION[stage]
    return math.floor(sanction_max_months * numerator / denominator)


def check_unfinished_offence_term(
    *,
    stage: OffenceStage,
    imposed_months: int | None,
    most_severe_max_months: int | None,
    imposed_most_severe_kind: bool,
    imposed_life_or_death: bool,
) -> CheckResult:
    """Candidate check of the imposed punishment against ч. 2–4 ст. 66 УК РФ."""

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)

    if stage is OffenceStage.COMPLETED:
        return result(CheckStatus.OK, "Преступление оконченное — ст. 66 УК РФ не применяется.")
    if stage is OffenceStage.UNKNOWN:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Стадия преступления не установлена — ограничения ст. 66 УК РФ не проверены.",
        )
    if imposed_life_or_death:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "За приготовление и покушение смертная казнь и пожизненное лишение свободы не "
            "назначаются (ч. 4 ст. 66 УК РФ).",
        )
    if not imposed_most_severe_kind:
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Назначен менее строгий вид наказания, чем наиболее строгий в санкции, — предел "
            "ст. 66 УК РФ для него не проверяется.",
        )
    if (
        imposed_months is None
        or imposed_months <= 0
        or most_severe_max_months is None
        or most_severe_max_months <= 0
    ):
        return result(
            CheckStatus.INSUFFICIENT_DATA,
            "Срок наказания или максимум санкции не определены.",
        )
    limit = unfinished_maximum(most_severe_max_months, stage)
    part, share = _PART[stage], _SHARE_GENITIVE[stage]
    if imposed_months <= limit:
        return result(
            CheckStatus.OK,
            f"Назначено {imposed_months} мес. — не более {share} максимума "
            f"({limit} из {most_severe_max_months} мес., {part} УК РФ).",
        )
    return result(
        CheckStatus.POSSIBLE_VIOLATION,
        f"Назначено {imposed_months} мес. — больше {share} максимума ({limit} из "
        f"{most_severe_max_months} мес.), {part} УК РФ.",
    )
