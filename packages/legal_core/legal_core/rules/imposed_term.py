# Domain Layer — is the imposed punishment within the statutory limits of the sanction?
# Limits: kind and bounds of the sanction of the article part, ч. 2–3 ст. 66 УК РФ (one half or
# three quarters of the maximum for an unfinished offence), ч. 1 ст. 62 УК РФ (two thirds of
# the most severe punishment) and ст. 64 УК РФ (below the minimum or a milder kind).
# Not checked here: ч. 5 ст. 62, ст. 65; ч. 2 ст. 68 is a separate check (rules/art68).
from fractions import Fraction

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import (
    ImposedPunishment,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
    StatutorySanction,
    Unfinished,
)
from legal_core.rules.art66 import NORMS as ART66_NORMS
from legal_core.rules.art66 import SHARE_WORDS, reduced_maximum

NORM = "Назначенное наказание: пределы санкции и ч. 1 ст. 62 УК РФ"
NOT_COVERED = "Не проверены ч. 5 ст. 62 и ст. 65 УК РФ; ч. 2 ст. 68 — отдельной проверкой."


def norm_of(unfinished: Unfinished | None, art62_applies: bool) -> str:
    """Only the limits that were actually applied are named."""
    limits = [ART66_NORMS[unfinished].removesuffix(" УК РФ")] if unfinished else []
    if art62_applies:
        limits.append("ч. 1 ст. 62")
    if not limits:
        return "Назначенное наказание: пределы санкции статьи УК РФ"
    named = limits[0] if len(limits) == 1 else f"{limits[0]} и {limits[1]}"
    joiner = " и " if len(limits) == 1 else ", "
    return f"Назначенное наказание: пределы санкции{joiner}{named} УК РФ"


_UNIT_NAMES = {
    MeasureUnit.MONTHS: "мес.",
    MeasureUnit.HOURS: "ч.",
    MeasureUnit.RUBLES: "руб.",
    MeasureUnit.DAYS: "дн.",
}


def main_imprisonment(sanctions: list[StatutorySanction]) -> StatutorySanction | None:
    return main_alternative(sanctions, PunishmentKind.IMPRISONMENT)


def main_alternative(
    sanctions: list[StatutorySanction], kind: PunishmentKind
) -> StatutorySanction | None:
    return next(
        (s for s in sanctions if s.kind is kind and s.role is SanctionRole.MAIN),
        None,
    )


def most_severe_alternative(sanctions: list[StatutorySanction]) -> StatutorySanction | None:
    main = [s for s in sanctions if s.role is SanctionRole.MAIN]
    order = list(PunishmentKind)
    return max(main, key=lambda s: order.index(s.kind)) if main else None


def _amount(value: float, unit: MeasureUnit) -> str:
    number = int(value) if float(value).is_integer() else value
    return f"{number} {_UNIT_NAMES[unit]}"


def check_imposed_punishment(
    imposed: PunishmentTerm,
    sanctions: list[StatutorySanction],
    *,
    source: str,
    art62_limit_months: int | None = None,
    art64_applied: bool = False,
    unfinished: Unfinished | None = None,
    art62_limit_amount: float | None = None,
) -> CheckResult:
    """Candidate check of one imposed main punishment against the sanction of its part.

    For an unfinished offence the caller passes art62_limit_months already taken of the reduced
    maximum (п. 49 Пленума ВС РФ № 58); the reduction itself is applied here to imprisonment.
    """
    norm = norm_of(unfinished, art62_limit_months is not None or art62_limit_amount is not None)

    def result(status: CheckStatus, why: str) -> CheckResult:
        return CheckResult(norm, status, f"{why} {NOT_COVERED}", source)

    alternative = main_alternative(sanctions, imposed.kind)
    if alternative is None:
        if art64_applied:
            return result(
                CheckStatus.OK, "Назначен вид наказания вне санкции со ссылкой на ст. 64 УК РФ."
            )
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Санкция этой части статьи не предусматривает назначенный вид наказания.",
        )
    if unfinished is not None and imposed.kind in (
        PunishmentKind.LIFE_IMPRISONMENT,
        PunishmentKind.DEATH_PENALTY,
    ):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Ч. 4 ст. 66 запрещает пожизненное лишение свободы и "
            "смертную казнь за неоконченное преступление.",
        )
    amount, unit = imposed.amount, imposed.unit
    if unit is MeasureUnit.DAYS and alternative.unit is MeasureUnit.MONTHS and amount is not None:
        amount, unit = Fraction(str(amount)) / 30, MeasureUnit.MONTHS
    if amount is None or alternative.unit is None or unit is not alternative.unit:
        return result(CheckStatus.INSUFFICIENT_DATA, "Размер наказания не сопоставлен с санкцией.")
    strongest = most_severe_alternative(sanctions)
    reducible = strongest is not None and (
        strongest.kind is imposed.kind
        or (
            imposed.kind is PunishmentKind.IMPRISONMENT
            and strongest.kind in (PunishmentKind.LIFE_IMPRISONMENT, PunishmentKind.DEATH_PENALTY)
        )
    )
    reduced = (
        reduced_maximum(alternative.max_value, unfinished)
        if reducible and unfinished and alternative.max_value
        else None
    )
    if alternative.max_value is not None and amount > alternative.max_value:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначено {_amount(amount, unit)} при максимуме санкции "
            f"{_amount(alternative.max_value, unit)}",
        )
    if (
        alternative.min_value is not None
        and amount < alternative.min_value
        and not art64_applied
        and not (reduced is not None and reduced <= alternative.min_value)
    ):
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначено {_amount(amount, unit)} ниже минимума санкции "
            f"{_amount(alternative.min_value, unit)} без применения ст. 64 УК РФ.",
        )
    months = amount if imposed.kind is PunishmentKind.IMPRISONMENT else None
    if reducible and unfinished is not None and alternative.max_value is not None:
        reduced = reduced_maximum(alternative.max_value, unfinished)
        if amount > reduced:
            return result(
                CheckStatus.POSSIBLE_VIOLATION,
                f"Назначено {_amount(amount, unit)} при пределе {_amount(reduced, unit)} "
                f"({SHARE_WORDS[unfinished]} "
                f"максимума, {ART66_NORMS[unfinished]}).",
            )
    if reducible and art62_limit_amount is not None and amount > art62_limit_amount:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначено {_amount(amount, unit)} при точном пределе "
            f"{_amount(art62_limit_amount, unit)} (ч. 1 ст. 62).",
        )
    if months is not None and art62_limit_months is not None and months > art62_limit_months:
        return result(
            CheckStatus.POSSIBLE_VIOLATION,
            f"Назначено {months} мес. при пределе {art62_limit_months} мес. "
            "(две трети максимума, ч. 1 ст. 62 УК РФ).",
        )
    return result(
        CheckStatus.OK, f"Назначено {_amount(amount, unit)}: в пределах проверенных ограничений."
    )


def check_imposed_imprisonment(
    imposed: ImposedPunishment,
    sanctions: list[StatutorySanction],
    *,
    source: str,
    art62_limit_months: int | None = None,
    art64_applied: bool = False,
) -> CheckResult:
    """Imprisonment-only variant used when the term comes from a model-cited fact."""
    months = imposed.imprisonment_months
    if months is None:
        return CheckResult(
            NORM,
            CheckStatus.INSUFFICIENT_DATA,
            f"Проверяется только лишение свободы. {NOT_COVERED}",
            source,
        )
    term = main_imprisonment(sanctions)
    if term is None or term.max_value is None:
        return CheckResult(
            NORM,
            CheckStatus.POSSIBLE_VIOLATION,
            f"Санкция этой части статьи не предусматривает лишения свободы. {NOT_COVERED}",
            source,
        )
    return check_imposed_punishment(
        PunishmentTerm(PunishmentKind.IMPRISONMENT, months, MeasureUnit.MONTHS),
        sanctions,
        source=source,
        art62_limit_months=art62_limit_months,
        art64_applied=art64_applied,
    )
