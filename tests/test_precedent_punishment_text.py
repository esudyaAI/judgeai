from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm

from src.services.sanction_summary import describe_precedent_punishment


def test_imprisonment_reads_term_first_and_marks_conditional():
    term = PunishmentTerm(PunishmentKind.IMPRISONMENT, 18, MeasureUnit.MONTHS)
    assert describe_precedent_punishment(term, True) == "1 г. 6 мес. лишения свободы, условно"
    assert describe_precedent_punishment(term, False) == "1 г. 6 мес. лишения свободы"


def test_other_kinds_are_named_with_their_amount():
    works = PunishmentTerm(PunishmentKind.COMPULSORY_WORKS, 220, MeasureUnit.HOURS)
    fine = PunishmentTerm(PunishmentKind.FINE, 104000, MeasureUnit.RUBLES)
    freedom = PunishmentTerm(PunishmentKind.RESTRICTION_OF_FREEDOM, 6, MeasureUnit.MONTHS)
    assert describe_precedent_punishment(works, False) == "Обязательные работы 220 ч."
    assert describe_precedent_punishment(fine, False) == "Штраф 104 000 ₽"
    assert describe_precedent_punishment(freedom, False) == "Ограничение свободы 6 мес."
    life = PunishmentTerm(PunishmentKind.LIFE_IMPRISONMENT)
    assert describe_precedent_punishment(life, False) == "Пожизненное лишение свободы"


def test_missing_punishment_is_said_plainly():
    assert describe_precedent_punishment(None, False) == "Наказание не распознано"
