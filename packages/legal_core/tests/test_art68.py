# Domain test — ч. 2 и 3 ст. 68 УК РФ (срок наказания при рецидиве).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art68 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    SOURCE,
    check_recidivism_term,
    part2_minimum_months,
)


@pytest.mark.parametrize(
    ("sanction_max", "expected"),
    [(60, 20), (24, 8), (120, 40), (12, 4), (52, 18), (7, 3), (1, 1)],
)
def test_one_third_rounded_up_to_whole_months(sanction_max, expected):
    # 52 / 3 = 17.33: 17 months would already be below one third, so the minimum is 18.
    assert part2_minimum_months(sanction_max) == expected


@pytest.mark.parametrize("bad", [0, -12])
def test_non_positive_maximum_is_rejected(bad):
    with pytest.raises(ValueError):
        part2_minimum_months(bad)


def _check(**overrides):
    params = {
        "recidivism": Recidivism.SIMPLE,
        "imposed_months": 20,
        "most_severe_max_months": 60,
        "imposed_most_severe_kind": True,
        "art61_mitigating_established": False,
        "art64_applied": False,
    }
    params.update(overrides)
    return check_recidivism_term(**params)


def test_result_is_marked_for_legal_review_with_source():
    result = _check()
    assert NEEDS_LEGAL_REVIEW is True
    assert result.needs_legal_review is True
    assert result.norm == NORM
    assert result.source == SOURCE
    assert "consultant.ru" in SOURCE and "04.08.2026" in SOURCE


@pytest.mark.parametrize(
    "kind", [Recidivism.SIMPLE, Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS]
)
def test_any_kind_of_recidivism_at_exactly_one_third_is_ok(kind):
    assert _check(recidivism=kind, imposed_months=20).status is CheckStatus.OK


def test_above_one_third_is_ok():
    assert _check(imposed_months=36).status is CheckStatus.OK


def test_below_one_third_without_grounds_is_flagged():
    result = _check(imposed_months=19)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "19" in result.explanation and "20" in result.explanation


def test_below_one_third_with_art61_mitigation_is_allowed_by_part3():
    result = _check(imposed_months=12, art61_mitigating_established=True)
    assert result.status is CheckStatus.OK
    assert "ч. 3 ст. 68" in result.explanation


def test_art64_lifts_part2_minimum_and_kind_restriction():
    result = _check(imposed_months=6, imposed_most_severe_kind=False, art64_applied=True)
    assert result.status is CheckStatus.OK
    assert "ст. 64" in result.explanation


def test_milder_kind_without_art64_is_flagged_even_with_mitigation():
    # Пленум ВС № 58, п. 47: a milder kind than the most severe one only under ст. 64.
    result = _check(
        imposed_months=None, imposed_most_severe_kind=False, art61_mitigating_established=True
    )
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 64" in result.explanation


def test_no_recidivism_means_rule_does_not_apply():
    result = _check(recidivism=Recidivism.NONE, imposed_months=1)
    assert result.status is CheckStatus.OK
    assert "не применяется" in result.explanation


def test_unknown_recidivism_gives_insufficient_data():
    assert _check(recidivism=Recidivism.UNKNOWN).status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize(("imposed", "maximum"), [(None, 60), (20, None), (20, 0), (-1, 60)])
def test_missing_or_invalid_terms_give_insufficient_data(imposed, maximum):
    result = _check(imposed_months=imposed, most_severe_max_months=maximum)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
