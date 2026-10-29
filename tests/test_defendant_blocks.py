from legal_core.entities import PunishmentKind

from src.application.precedent_cards import build_cards
from src.infrastructure.verdict_reader import PracticeReader
from src.services.defendant_blocks import split_defendants
from tests.fixtures.synthetic_verdicts import PRACTICE_THEFT, PRACTICE_TWO_DEFENDANTS


def test_one_block_per_convicted_person_in_order():
    operative = (
        "А. признать виновным в краже и назначить 120 часов обязательных работ.\n"
        "Б. признать виновной в краже и назначить штраф.\n"
        "Меру пресечения А. и Б. отменить."
    )
    blocks = split_defendants(operative)
    assert [b[:2] for b in blocks] == ["А.", "Б."]
    assert "".join(blocks) == operative


def test_further_counts_of_the_same_person_stay_together():
    operative = (
        "ФИО4 признать виновным в совершении преступления по ч. 2 ст. 159.5 УК РФ.\n"
        "Его же признать виновным в совершении преступления по ч. 3 ст. 159.5 УК РФ.\n"
        "ФИО4 признать виновным в совершении преступления по ч. 1 ст. 159 УК РФ."
    )
    assert split_defendants(operative) == [operative]


def test_both_word_orders_and_an_acquitted_person_is_not_a_block():
    operative = (
        "Признать Иванова И.И. виновным в краже.\n"
        "Признать Петрова П.П. невиновным и оправдать.\n"
        "Признать Сидорова С.С. виновным в грабеже."
    )
    blocks = split_defendants(operative)
    assert len(blocks) == 2 and blocks[1].startswith("Признать Сидорова")


def test_practice_verdict_on_two_people_gives_each_a_card_with_own_punishment():
    works, prison = (e.card for e in build_cards(PracticeReader(), PRACTICE_TWO_DEFENDANTS))
    assert (works.punishment.kind, works.punishment.amount) == (
        PunishmentKind.COMPULSORY_WORKS,
        120,
    )
    assert works.conditional is False
    assert (prison.imprisonment_months, prison.conditional) == (12, True)


def test_verdict_on_one_person_keeps_one_card():
    assert len(build_cards(PracticeReader(), PRACTICE_THEFT)) == 1


def test_conviction_before_name_keeps_people_and_sentences_separate():
    from src.services.defendant_blocks import defendant_names

    operative = (
        "Признать виновным ФИО1 в совершении преступления по ч. 1 ст. 158 УК РФ.\n"
        "Назначить наказание в виде лишения свободы сроком на 1 год.\n"
        "Признать виновным ФИО2 виновным в совершении преступления по ч. 1 ст. 159 УК РФ.\n"
        "Назначить наказание в виде лишения свободы сроком на 3 года."
    )
    assert defendant_names(operative) == ["фио1", "фио2"]
    cards = build_cards(
        PracticeReader(), "УСТАНОВИЛА:\nОбстоятельства.\nПРИГОВОРИЛА:\n" + operative
    )
    assert [c.card.imprisonment_months for c in cards] == [12, 36]
    assert [c.card.main_qualification.article for c in cards] == ["158", "159"]


def test_wrapped_identity_does_not_become_a_previous_punishment_paragraph():
    from src.services.defendant_blocks import defendant_names

    operative = (
        "ФИО1\nпризнать виновным в краже.\n"
        "Назначить наказание в виде лишения свободы сроком на 1 год.\n"
        "ФИО2\nпризнать виновным в грабеже."
    )
    assert defendant_names(operative) == ["фио1", "фио2"]
    assert len(split_defendants(operative)) == 2
