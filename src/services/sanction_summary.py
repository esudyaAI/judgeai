"""Presentation: short Russian description of statutory sanctions for reports and the UI."""

from legal_core.entities import (
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
    StatutorySanction,
)

_KIND_NAMES = {
    PunishmentKind.FINE: "штраф",
    PunishmentKind.DEPRIVATION_OF_RIGHT: (
        "лишение права занимать должности или заниматься деятельностью"
    ),
    PunishmentKind.COMPULSORY_WORKS: "обязательные работы",
    PunishmentKind.CORRECTIONAL_WORKS: "исправительные работы",
    PunishmentKind.MILITARY_SERVICE_RESTRICTION: "ограничение по военной службе",
    PunishmentKind.RESTRICTION_OF_FREEDOM: "ограничение свободы",
    PunishmentKind.FORCED_LABOUR: "принудительные работы",
    PunishmentKind.ARREST: "арест",
    PunishmentKind.DISCIPLINARY_MILITARY_UNIT: "содержание в дисциплинарной воинской части",
    PunishmentKind.IMPRISONMENT: "лишение свободы",
    PunishmentKind.LIFE_IMPRISONMENT: "пожизненное лишение свободы",
    PunishmentKind.DEATH_PENALTY: "смертная казнь",
}


def format_amount(value: float, unit: MeasureUnit) -> str:
    if unit is MeasureUnit.RUBLES:
        return f"{int(value):,} ₽".replace(",", " ")
    if unit is MeasureUnit.HOURS:
        return f"{int(value)} ч."
    years, months = divmod(int(value), 12)
    parts = ([f"{years} г."] if years else []) + ([f"{months} мес."] if months else [])
    return " ".join(parts) or "0 мес."


def describe_sanction(sanction: StatutorySanction) -> str:
    name = _KIND_NAMES[sanction.kind]
    if sanction.unit is None:
        return name
    low = f"от {format_amount(sanction.min_value, sanction.unit)} " if sanction.min_value else ""
    high = f"до {format_amount(sanction.max_value, sanction.unit)}" if sanction.max_value else ""
    return f"{name} {low}{high}".strip()


def describe_main_alternatives(sanctions: list[StatutorySanction]) -> str:
    main = [describe_sanction(s) for s in sanctions if s.role is SanctionRole.MAIN]
    return "; ".join(dict.fromkeys(main))


def describe_precedent_punishment(term: PunishmentTerm | None, conditional: bool) -> str:
    """Punishment of a similar verdict: '1 г. 6 мес. лишения свободы, условно', 'Штраф 5 000 ₽'."""
    if term is None:
        return "Наказание не распознано"
    if term.kind is PunishmentKind.IMPRISONMENT and term.unit is MeasureUnit.MONTHS:
        text = f"{format_amount(term.amount, term.unit)} лишения свободы"
    else:
        name = describe_term(term)
        text = name[:1].upper() + name[1:]
    return f"{text}, условно" if conditional else text


def describe_term(term: PunishmentTerm) -> str:
    """'лишение свободы 2 г. 6 мес.' for an imposed punishment."""
    name = _KIND_NAMES[term.kind]
    if term.amount is None or term.unit is None:
        return name
    return f"{name} {format_amount(term.amount, term.unit)}"
