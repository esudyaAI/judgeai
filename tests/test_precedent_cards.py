from legal_core.entities import MeasureUnit, PunishmentKind
from legal_core.precedents import Qualification, Recidivism

from src.application.precedent_cards import CARD_EXTRACTOR_VERSION, build_card
from src.domain.extraction import ExtractionMethod
from src.infrastructure.circumstance_extractor import extract_circumstances
from src.infrastructure.fabula import extract_fabula
from src.infrastructure.verdict_reader import RegexVerdictReader
from tests.fixtures.synthetic_verdicts import (
    MULTI_COUNT,
    NO_HEADINGS,
    PRACTICE_ROBBERY,
    PRACTICE_THEFT,
)

READER = RegexVerdictReader()


def _fields(extraction):
    return {f.name: f for f in extraction.fields}


def test_practice_theft_card():
    extraction = build_card(READER, PRACTICE_THEFT)
    card = extraction.card
    assert card.main_qualification == Qualification("158", 2, "в")
    assert card.episodes[0].punishment.amount == 18
    assert card.episodes[0].punishment.kind is PunishmentKind.IMPRISONMENT
    assert card.mitigating == {"61.1.и", "61.1.к", "61.2"}
    assert card.aggravating == frozenset()
    assert card.applied_general == {"62.1", "73"}
    assert card.recidivism is Recidivism.NONE
    assert card.conditional is True
    assert card.imprisonment_months == 18
    assert card.fabula.startswith("М. 3 февраля 2026 года") and "вину признал" not in card.fabula


def test_fields_registry_has_method_quote_version_and_hash():
    extraction = build_card(READER, PRACTICE_THEFT)
    fields = _fields(extraction)
    assert set(fields) == {
        "qualifications",
        "counts",
        "final_sentence",
        "conditional",
        "mitigating",
        "aggravating",
        "applied_general",
        "recidivism",
        "fabula",
    }
    assert fields["mitigating"].method is ExtractionMethod.REGEX
    assert "явку с повинной" in fields["mitigating"].quote
    assert fields["aggravating"].method is ExtractionMethod.NONE
    assert fields["final_sentence"].method is ExtractionMethod.NONE
    assert {f.extractor_version for f in extraction.fields} == {CARD_EXTRACTOR_VERSION}
    assert {f.input_hash for f in extraction.fields} == {extraction.text_hash}
    for field in extraction.fields:
        if field.method is ExtractionMethod.REGEX:
            for piece in field.quote.split(" … "):
                assert piece[:40] in PRACTICE_THEFT


def test_dangerous_recidivism_and_rule_68():
    card = build_card(READER, PRACTICE_ROBBERY).card
    assert card.recidivism is Recidivism.DANGEROUS
    assert card.aggravating == {"63.1.а"}
    assert card.mitigating == frozenset()
    assert card.applied_general == {"68.2"}
    assert card.main_qualification == Qualification("161", 1)


def test_multi_count_card_has_episode_per_count_and_final():
    card = build_card(READER, MULTI_COUNT).card
    assert [e.qualification.key for e in card.episodes] == ["158/3/г", "158/2/в"]
    assert card.final.amount == 36 and card.final.unit is MeasureUnit.MONTHS
    assert card.recidivism is Recidivism.SIMPLE
    assert "61.1.и" in card.mitigating and "63.1.а" in card.aggravating


def test_unstructured_text_gives_empty_card_not_error():
    extraction = build_card(READER, NO_HEADINGS)
    assert extraction.card.episodes == ()
    assert _fields(extraction)["qualifications"].method is ExtractionMethod.NONE


def test_circumstances_negations_and_other_mentions():
    reading = extract_circumstances(
        "Потерпевший написал явку с повинной на другого человека. "
        "Обстоятельств, смягчающих наказание, суд не усматривает. "
        "Обстоятельством, отягчающим наказание, является совершение преступления в состоянии "
        "опьянения, вызванном употреблением алкоголя (ч. 1.1 ст. 63 УК РФ)."
    )
    assert reading.mitigating == {}
    assert set(reading.aggravating) == {"63.1.1"}
    assert reading.recidivism is None


def test_especially_dangerous_recidivism():
    reading = extract_circumstances("В действиях Т. имеется особо опасный рецидив преступлений.")
    assert reading.recidivism is Recidivism.ESPECIALLY_DANGEROUS


def test_fabula_without_marker_is_beginning():
    assert extract_fabula("  Кража телефона.  ") == "Кража телефона."


def test_query_card_needs_some_text():
    from src.application.precedent_cards import query_card

    reader = RegexVerdictReader()
    assert query_card(reader, []) is None
    assert query_card(reader, ["", "  \n "]) is None


def test_query_card_prefers_the_document_with_a_qualification():
    from src.application.precedent_cards import query_card

    card = query_card(RegexVerdictReader(), [NO_HEADINGS, PRACTICE_THEFT])
    assert [str(e.qualification) for e in card.episodes] == ["п. «в» ч. 2 ст. 158 УК РФ"]


def test_wholly_acquittal_is_not_conviction_practice():
    from src.application.precedent_cards import build_cards
    from src.infrastructure.verdict_reader import PracticeReader

    for decision in (
        "Оправдать ФИО1 по предъявленному обвинению по ч. 1 ст. 158 УК РФ.",
        "Признать ФИО1 невиновным и оправдать по ч. 1 ст. 158 УК РФ.",
        "ФИО1 по предъявленному обвинению по ч. 1 ст. 158 УК РФ оправдать.",
    ):
        text = "ПРИГОВОР\nУСТАНОВИЛ:\nОбвинялся по ч. 1 ст. 158 УК РФ.\nПРИГОВОРИЛ:\n" + decision
        assert build_cards(PracticeReader(), text) == []


def test_acquittal_request_does_not_hide_a_conviction():
    from src.application.precedent_cards import build_cards
    from src.infrastructure.verdict_reader import PracticeReader

    text = (
        "УСТАНОВИЛ:\nЗащитник просил оправдать ФИО1.\nПРИГОВОРИЛ:\n"
        "Признать ФИО1 виновным по ч. 1 ст. 158 УК РФ и назначить "
        "наказание в виде лишения свободы сроком на 1 год."
    )
    assert len(build_cards(PracticeReader(), text)) == 1
