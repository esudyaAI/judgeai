"""Readers of the facts ч. 1 ст. 58 needs: regime, sex, previous imprisonment (synthetic texts)."""

import pytest
from legal_core.rules.art58 import Regime

from src.services.regime_facts import read_male, read_regime, read_served_before


@pytest.mark.parametrize(
    ("text", "regime"),
    [
        ("с отбыванием наказания в исправительной колонии общего режима", Regime.GENERAL),
        ("в исправительной колонии строгого режима", Regime.STRICT),
        ("в Исправительной колонии особого режима", Regime.SPECIAL),
        ("с отбыванием наказания в колонии-поселении", Regime.SETTLEMENT),
        ("следовать в колонию-поселение самостоятельно", Regime.SETTLEMENT),
    ],
)
def test_regime_is_read(text, regime):
    found, quote = read_regime(text)
    assert found is regime and quote


def test_last_mention_wins_over_the_history_in_the_introduction():
    text = (
        "ранее отбывал наказание в исправительной колонии строгого режима ... "
        "назначить наказание с отбыванием в исправительной колонии особого режима"
    )
    assert read_regime(text)[0] is Regime.SPECIAL


def test_no_regime_when_none_is_named():
    assert read_regime("назначить наказание условно") == (None, "")


@pytest.mark.parametrize(
    ("text", "male"),
    [
        ("Подсудимый Иванов вину признал. Признать Иванова виновным", True),
        ("Подсудимая Иванова вину признала. Признать Иванову виновной", False),
        ("гражданка РФ, ранее не судимая", False),
        ("Свидетель показал", None),
    ],
)
def test_sex_from_grammatical_forms(text, male):
    assert read_male(text)[0] is male


def test_mixed_forms_need_a_clear_majority():
    text = "Подсудимый ... подсудимый ... подсудимого ... свидетель гражданка Петрова"
    assert read_male(text)[0] is True
    assert read_male("подсудимый ... подсудимая")[0] is None


@pytest.mark.parametrize(
    ("text", "served"),
    [
        ("ранее отбывавший наказание в виде лишения свободы", True),
        ("отбывал лишение свободы в ИК-3", True),
        ("освобожден 12.03.2020 по отбытии срока из ИК-3", True),
        ("освобождён из мест лишения свободы", True),
        ("освобожден по отбытии наказания", None),  # also follows non-custodial punishments
        ("ранее не отбывавший лишение свободы", False),
        ("не отбывал наказание в виде лишения свободы", False),
        ("ранее не судимый", False),
        ("ранее судим", None),
    ],
)
def test_previous_imprisonment_by_explicit_phrases(text, served):
    assert read_served_before(text)[0] is served


def test_explicit_negative_wins():
    text = "ранее судим, освобожден из ИК-2; ранее не отбывавший лишение свободы"
    assert read_served_before(text)[0] is False
