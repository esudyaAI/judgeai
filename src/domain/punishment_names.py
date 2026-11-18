"""Russian names of the kinds of punishment of art. 44 УК РФ, as the user reads them.

These are the labels of the legal_core enum, not data about sanctions: the bounds of every
sanction come from the imported statute in the database.
"""

from legal_core.entities import PunishmentKind

PUNISHMENT_NAMES = {
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
