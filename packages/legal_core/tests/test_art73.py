# Domain test — ст. 73 УК РФ (условное осуждение).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art73 import (
    NEEDS_LEGAL_REVIEW,
    ConditionalKind,
    check_conditional_sentence,
    probation_bounds,
)

IMPRISONMENT = ConditionalKind.IMPRISONMENT


def _check(**overrides):
    params = {
        "conditional": True,
        "kind": IMPRISONMENT,
        "imprisonment_months": 24,
        "probation_months": 24,
        "recidivism": Recidivism.NONE,
    }
    params.update(overrides)
    return check_conditional_sentence(**params)


@pytest.mark.parametrize(
    ("kind", "months", "bounds"),
    [
        (IMPRISONMENT, 12, (6, 36)),
        (IMPRISONMENT, 13, (6, 60)),
        (IMPRISONMENT, 96, (6, 60)),
        (ConditionalKind.CORRECTIONAL_LABOUR, None, (6, 36)),
        (IMPRISONMENT, None, None),
    ],
)
def test_probation_bounds_by_part_3(kind, months, bounds):
    assert probation_bounds(kind, months) == bounds


def test_real_sentence_is_not_checked():
    result = _check(conditional=False, recidivism=Recidivism.ESPECIALLY_DANGEROUS)
    assert result.status is CheckStatus.OK
    assert NEEDS_LEGAL_REVIEW is True and result.needs_legal_review is True


def test_lawful_conditional_sentence_is_ok():
    result = _check()
    assert result.status is CheckStatus.OK
    assert "«а.1»" in result.explanation  # reminds that these items were not checked


@pytest.mark.parametrize("months", [96, 1])
def test_up_to_eight_years_may_be_conditional(months):
    assert _check(imprisonment_months=months, probation_months=12).status is CheckStatus.OK


def test_over_eight_years_cannot_be_conditional():
    result = _check(imprisonment_months=97)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "8 лет" in result.explanation


def test_other_kinds_cannot_be_conditional():
    result = _check(kind=ConditionalKind.OTHER, imprisonment_months=None, probation_months=12)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


@pytest.mark.parametrize("recidivism", [Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS])
def test_dangerous_recidivism_excludes_conditional_sentence(recidivism):
    result = _check(recidivism=recidivism)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «в»" in result.explanation


def test_simple_recidivism_does_not_exclude_it():
    assert _check(recidivism=Recidivism.SIMPLE).status is CheckStatus.OK


@pytest.mark.parametrize(("months", "probation"), [(12, 37), (12, 5), (24, 61), (24, 5)])
def test_probation_outside_part_3_is_flagged(months, probation):
    result = _check(imprisonment_months=months, probation_months=probation)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 3 ст. 73" in result.explanation


def test_items_established_by_the_caller_are_reported():
    result = _check(other_exclusions=["а.1", "unknown"])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «а.1»" in result.explanation and "unknown" not in result.explanation


@pytest.mark.parametrize(
    "overrides",
    [
        {"recidivism": Recidivism.UNKNOWN},
        {"probation_months": None},
        {"imprisonment_months": None},
    ],
)
def test_missing_data_gives_insufficient_data(overrides):
    assert _check(**overrides).status is CheckStatus.INSUFFICIENT_DATA


def test_violation_wins_over_missing_data():
    result = _check(recidivism=Recidivism.DANGEROUS, probation_months=None)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
