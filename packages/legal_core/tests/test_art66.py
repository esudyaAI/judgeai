# Domain test — ч. 2–4 ст. 66 УК РФ (наказание за неоконченное преступление).
import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import Unfinished
from legal_core.rules.art66 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    RULE_KEY,
    SOURCE,
    OffenceStage,
    check_unfinished_offence_term,
    reduced_maximum,
    unfinished_maximum,
)


@pytest.mark.parametrize(
    ("maximum", "expected"),
    [(120, 60), (60, 30), (15, 7), (1, 0), (72, 36)],
)
def test_preparation_is_capped_at_half_rounded_down(maximum, expected):
    # 15 / 2 = 7.5: a whole-month term of 8 months would already exceed one half.
    assert unfinished_maximum(maximum, OffenceStage.PREPARATION) == expected


@pytest.mark.parametrize(
    ("maximum", "expected"),
    [(120, 90), (60, 45), (10, 7), (72, 54), (1, 0)],
)
def test_attempt_is_capped_at_three_quarters_rounded_down(maximum, expected):
    # 10 * 3 / 4 = 7.5: 8 months would already exceed three quarters.
    assert unfinished_maximum(maximum, OffenceStage.ATTEMPT) == expected


def test_completed_offence_keeps_the_sanction_maximum():
    assert unfinished_maximum(60, OffenceStage.COMPLETED) == 60


def test_unknown_stage_gives_no_maximum():
    # The stage is a fact of the verdict; an unknown fact never becomes a default limit.
    assert unfinished_maximum(60, OffenceStage.UNKNOWN) is None


@pytest.mark.parametrize("bad", [0, -6])
def test_non_positive_maximum_is_rejected(bad):
    with pytest.raises(ValueError):
        unfinished_maximum(bad, OffenceStage.ATTEMPT)


def _check(**overrides):
    params = {
        "stage": OffenceStage.ATTEMPT,
        "imposed_months": 45,
        "most_severe_max_months": 60,
        "imposed_most_severe_kind": True,
        "imposed_life_or_death": False,
    }
    params.update(overrides)
    return check_unfinished_offence_term(**params)


def test_result_carries_norm_source_review_flag_and_rule_key():
    result = _check()
    assert result.norm == NORM
    assert result.source == SOURCE
    assert result.needs_legal_review is NEEDS_LEGAL_REVIEW is True
    assert result.rule_key == RULE_KEY == "art66.unfinished_offence"
    assert "ст. 66" in NORM


def test_completed_offence_is_outside_art66():
    result = _check(stage=OffenceStage.COMPLETED, imposed_months=60)
    assert result.status is CheckStatus.OK
    assert "оконч" in result.explanation


def test_unknown_stage_is_insufficient_data():
    result = _check(stage=OffenceStage.UNKNOWN)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "стадия" in result.explanation.lower()


@pytest.mark.parametrize("stage", [OffenceStage.ATTEMPT, OffenceStage.PREPARATION])
def test_life_or_death_for_unfinished_offence_is_flagged_under_part4(stage):
    result = _check(stage=stage, imposed_life_or_death=True, imposed_months=None)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 4 ст. 66" in result.explanation


def test_attempt_at_the_limit_is_ok():
    result = _check(imposed_months=45)
    assert result.status is CheckStatus.OK
    assert "45" in result.explanation and "60" in result.explanation


def test_attempt_above_three_quarters_is_flagged():
    result = _check(imposed_months=46)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 3 ст. 66" in result.explanation
    assert "45" in result.explanation


def test_preparation_above_half_is_flagged_under_part2():
    result = _check(stage=OffenceStage.PREPARATION, imposed_months=31)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 2 ст. 66" in result.explanation
    assert "30" in result.explanation


def test_preparation_at_half_is_ok():
    assert _check(stage=OffenceStage.PREPARATION, imposed_months=30).status is CheckStatus.OK


def test_half_of_one_month_leaves_no_whole_month_term():
    result = _check(stage=OffenceStage.PREPARATION, imposed_months=1, most_severe_max_months=1)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_milder_kind_is_not_checked_against_the_most_severe_maximum():
    result = _check(imposed_most_severe_kind=False, imposed_months=100)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "менее строг" in result.explanation


@pytest.mark.parametrize(
    "overrides",
    [
        {"imposed_months": None},
        {"imposed_months": 0},
        {"most_severe_max_months": None},
        {"most_severe_max_months": 0},
    ],
)
def test_missing_term_or_maximum_is_insufficient_data(overrides):
    assert _check(**overrides).status is CheckStatus.INSUFFICIENT_DATA


# --- reduced_maximum (stage as entities.Unfinished, used by the analysis) ---
def test_attempt_and_preparation_reduce_the_maximum():
    assert reduced_maximum(48, Unfinished.ATTEMPT) == 36
    assert reduced_maximum(48, Unfinished.PREPARATION) == 24
    assert reduced_maximum(10, Unfinished.ATTEMPT) == 7.5


def test_completed_offence_keeps_the_maximum():
    assert reduced_maximum(48, None) == 48


def test_maximum_must_be_positive():
    with pytest.raises(ValueError):
        reduced_maximum(0, Unfinished.ATTEMPT)
