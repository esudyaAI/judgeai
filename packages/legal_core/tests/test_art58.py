# Domain test — ч. 1 ст. 58 УК РФ (вид исправительного учреждения).
import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import NEEDS_LEGAL_REVIEW, Regime, check_regime, expected_regimes

INT, NEG = Guilt.INTENTIONAL, Guilt.NEGLIGENT
SMALL, MEDIUM, GRAVE, EXTRA = (
    Category.SMALL,
    Category.MEDIUM,
    Category.GRAVE,
    Category.ESPECIALLY_GRAVE,
)
R = Recidivism


@pytest.mark.parametrize(
    ("guilt", "category", "male", "recidivism", "served", "expected"),
    [
        # п. «а»: неосторожные; умышленные небольшой/средней, ранее не отбывал
        (NEG, GRAVE, True, R.NONE, True, {Regime.SETTLEMENT, Regime.GENERAL}),
        (INT, MEDIUM, True, R.NONE, False, {Regime.SETTLEMENT, Regime.GENERAL}),
        (INT, SMALL, False, R.SIMPLE, False, {Regime.SETTLEMENT, Regime.GENERAL}),
        # п. «б»: мужчины — тяжкие, ранее не отбывал; женщины — тяжкие и особо тяжкие
        (INT, GRAVE, True, R.NONE, False, {Regime.GENERAL}),
        (INT, GRAVE, True, R.SIMPLE, False, {Regime.GENERAL}),
        (INT, EXTRA, False, R.DANGEROUS, True, {Regime.GENERAL}),
        # п. «в»: мужчины — особо тяжкие, ранее не отбывал; рецидив/опасный и ранее отбывал
        (INT, EXTRA, True, R.NONE, False, {Regime.STRICT}),
        (INT, MEDIUM, True, R.SIMPLE, True, {Regime.STRICT}),
        (INT, GRAVE, True, R.DANGEROUS, True, {Regime.STRICT}),
        # п. «г»: мужчины — особо опасный рецидив
        (INT, EXTRA, True, R.ESPECIALLY_DANGEROUS, True, {Regime.SPECIAL}),
    ],
)
def test_expected_regime_by_part_1(guilt, category, male, recidivism, served, expected):
    regimes, _ = expected_regimes(
        guilt=guilt,
        category=category,
        male=male,
        recidivism=recidivism,
        served_imprisonment_before=served,
    )
    assert regimes == expected


def test_life_imprisonment_of_a_man_is_special_regime():
    regimes, _ = expected_regimes(
        guilt=INT,
        category=EXTRA,
        male=True,
        recidivism=R.NONE,
        served_imprisonment_before=False,
        life_imprisonment=True,
    )
    assert regimes == {Regime.SPECIAL}


@pytest.mark.parametrize(
    ("guilt", "category", "male", "recidivism", "served"),
    [
        (INT, GRAVE, True, R.NONE, True),  # мужчина, ранее отбывал, без рецидива
        (INT, MEDIUM, False, R.NONE, True),  # женщина, ранее отбывала, средней тяжести
    ],
)
def test_cases_outside_the_text_are_not_guessed(guilt, category, male, recidivism, served):
    assert (
        expected_regimes(
            guilt=guilt,
            category=category,
            male=male,
            recidivism=recidivism,
            served_imprisonment_before=served,
        )
        is None
    )


def _check(**overrides):
    params = {
        "imposed": Regime.GENERAL,
        "guilt": INT,
        "category": GRAVE,
        "male": True,
        "recidivism": R.NONE,
        "served_imprisonment_before": False,
    }
    params.update(overrides)
    return check_regime(**params)


def test_matching_regime_is_ok():
    result = _check()
    assert result.status is CheckStatus.OK
    assert NEEDS_LEGAL_REVIEW is True and result.needs_legal_review is True


def test_wrong_regime_is_flagged_with_the_expected_one():
    result = _check(imposed=Regime.STRICT)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "колония общего режима" in result.explanation


def test_general_instead_of_settlement_needs_motivation():
    result = _check(category=MEDIUM)
    assert result.status is CheckStatus.OK
    assert "мотивировк" in result.explanation


def test_settlement_where_allowed_is_ok_without_note():
    result = _check(category=MEDIUM, imposed=Regime.SETTLEMENT)
    assert result.status is CheckStatus.OK and "мотивировк" not in result.explanation


@pytest.mark.parametrize(
    "overrides",
    [
        {"imposed": None},
        {"male": None},
        {"category": None},
        {"guilt": None},
        {"served_imprisonment_before": None},
        {"recidivism": R.UNKNOWN},
    ],
)
def test_missing_facts_give_insufficient_data(overrides):
    assert _check(**overrides).status is CheckStatus.INSUFFICIENT_DATA


def test_case_outside_the_text_gives_insufficient_data():
    result = _check(served_imprisonment_before=True)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "Пленума" in result.explanation
