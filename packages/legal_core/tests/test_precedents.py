import pytest

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from legal_core.precedents import (
    PrecedentCard,
    PrecedentEpisode,
    Qualification,
    Recidivism,
    parse_qualifications,
)


def test_qualification_key_and_text():
    q = Qualification("158", 2, "в")
    assert q.key == "158/2/в"
    assert Qualification("228.1", 4).key == "228.1/4"
    assert str(q) == "п. «в» ч. 2 ст. 158 УК РФ"
    assert Qualification("105").key == "105"
    assert str(Qualification("228.1", 4)) == "ч. 4 ст. 228.1 УК РФ"


def test_qualification_rejects_general_part_and_empty_point():
    with pytest.raises(ValueError):
        Qualification("62", 1)
    with pytest.raises(ValueError):
        Qualification("158", 2, "")


def test_parse_qualifications_expands_several_points_and_skips_general_part():
    found = parse_qualifications(
        "п. «г» ч. 3 ст. 158, п.п. «в, г» ч. 2 ст. 158, ч. 3 ст. 30, ч. 1 ст. 161 УК РФ"
    )
    assert found == (
        Qualification("158", 3, "г"),
        Qualification("158", 2, "в"),
        Qualification("158", 2, "г"),
        Qualification("161", 1),
    )


def test_parse_qualifications_ignores_other_codes_and_duplicates():
    assert parse_qualifications("ст. 307 УПК РФ") == ()
    assert parse_qualifications("ч. 1 ст. 158 и ч. 1 ст. 158 УК РФ") == (Qualification("158", 1),)
    assert parse_qualifications("") == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # sudact/OCR texts drop the article dot: "ст. 2281" is ст. 228.1.
        ("ч. 2 ст. 3141 УК РФ", (Qualification("314.1", 2),)),
        ("ПРИГОВОРИЛ: …предусмотренного ч. 3 ст. 2581 УК РФ…", (Qualification("258.1", 3),)),
        ("пунктом «г» части 4 статьи 2281 УК РФ", (Qualification("228.1", 4, "г"),)),
        ("ст. 1581 УК РФ", (Qualification("158.1", None),)),
        # dotted and plain forms are unaffected
        ("ч. 4 ст. 228.1 УК РФ", (Qualification("228.1", 4),)),
        ("ч. 1 ст. 158 УК РФ", (Qualification("158", 1),)),
    ],
)
def test_parse_qualifications_restores_dropped_article_dot(text, expected):
    assert parse_qualifications(text) == expected


def _card(**kw):
    base = dict(
        episodes=(PrecedentEpisode(Qualification("158", 2, "в"), None),),
        mitigating=frozenset({"61.1.и"}),
        aggravating=frozenset(),
        recidivism=Recidivism.NONE,
        applied_general=frozenset({"62.1"}),
        final=None,
        conditional=False,
        fabula="тайно похитил ноутбук",
    )
    base.update(kw)
    return PrecedentCard(**base)


def test_card_main_qualification_and_imprisonment():
    term = PunishmentTerm(PunishmentKind.IMPRISONMENT, 18, MeasureUnit.MONTHS)
    card = _card(final=term)
    assert card.main_qualification == Qualification("158", 2, "в")
    assert card.qualification_keys == frozenset({"158/2/в"})
    assert card.imprisonment_months == 18


def test_card_imprisonment_from_single_episode_and_none_for_other_kinds():
    term = PunishmentTerm(PunishmentKind.IMPRISONMENT, 24, MeasureUnit.MONTHS)
    card = _card(episodes=(PrecedentEpisode(Qualification("158", 2, "в"), term),))
    assert card.imprisonment_months == 24
    fine = PunishmentTerm(PunishmentKind.FINE, 5000, MeasureUnit.RUBLES)
    assert _card(final=fine).imprisonment_months is None


def test_card_without_episodes_has_no_main_qualification():
    card = _card(episodes=())
    assert card.main_qualification is None
    assert card.imprisonment_months is None


def test_card_rejects_unknown_circumstance_codes():
    with pytest.raises(ValueError):
        _card(mitigating=frozenset({"явка"}))


def test_parse_qualifications_reads_part_and_article_in_words():
    assert parse_qualifications("предусмотренного частью 1 статьи 222 УК РФ") == (
        Qualification("222", 1),
    )
    assert parse_qualifications("пунктом «а» части 2 статьи 158 УК РФ") == (
        Qualification("158", 2, "а"),
    )
    assert parse_qualifications("статьей 73 УК РФ") == ()


def test_card_punishment_is_final_or_the_single_count_of_any_kind():
    works = PunishmentTerm(PunishmentKind.COMPULSORY_WORKS, 220, MeasureUnit.HOURS)
    single = _card(episodes=(PrecedentEpisode(Qualification("264.1", 1), works),))
    assert single.punishment == works
    assert single.imprisonment_months is None
    two = (
        PrecedentEpisode(Qualification("158", 1), works),
        PrecedentEpisode(Qualification("159", 1), works),
    )
    assert _card(episodes=two).punishment is None
    fine = PunishmentTerm(PunishmentKind.FINE, 5000, MeasureUnit.RUBLES)
    assert _card(episodes=two, final=fine).punishment == fine
