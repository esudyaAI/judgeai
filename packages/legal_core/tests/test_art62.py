# Domain test — ч. 1 ст. 62 УК РФ (предел при смягчающих п. «и», «к» ч. 1 ст. 61).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art62 import (
    NEEDS_LEGAL_REVIEW,
    NORM_PART5,
    RULE_KEY_PART5,
    SOURCE_PART5,
    ProcedureKind,
    check_procedure_term,
    has_part1_mitigation,
    part1_limit_months,
    procedure_maximum,
)

I_ITEM = "п. «и» ч. 1 ст. 61"


@pytest.mark.parametrize(
    ("norm", "expected"),
    [
        ("п. «и» ч. 1 ст. 61", True),
        ("п. «к» ч. 1 ст. 61 УК РФ", True),
        ("п. «г», «и» ч. 1 ст. 61", True),
        ("пп. «и», «к» ч.1 ст.61", True),
        ("П. «И» Ч. 1 СТ. 61", True),
        ("п. «г» ч. 1 ст. 61", False),
        ("ч. 2 ст. 61", False),
        ("п. «и» ч. 1 ст. 63", False),
        ("п. «к» ч. 1 ст. 610", False),
        ("п. «и» ч. 1 ст. 61.1", False),
        ("", False),
    ],
)
def test_detects_art61_part1_items_i_k(norm, expected):
    assert has_part1_mitigation([norm]) is expected


def test_any_of_several_norms_is_enough():
    assert has_part1_mitigation(["ч. 2 ст. 61", I_ITEM]) is True
    assert has_part1_mitigation([]) is False


def test_two_thirds_of_sanction_maximum():
    assert part1_limit_months(60, [I_ITEM], has_aggravating=False) == 40


def test_rounded_down_never_above_two_thirds():
    # 2/3 of 52 months = 34.67 -> 34; 35 would exceed the statutory cap.
    assert part1_limit_months(52, ["п. «к» ч. 1 ст. 61"], has_aggravating=False) == 34
    assert part1_limit_months(1, [I_ITEM], has_aggravating=False) == 0


@pytest.mark.parametrize(
    ("sanction_max", "norms", "has_aggravating"),
    [
        (60, [I_ITEM], True),  # aggravating circumstances exclude the rule
        (60, ["ч. 2 ст. 61"], False),  # no item «и» / «к»
        (60, [], False),
        (0, [I_ITEM], False),  # no imprisonment maximum to take two thirds of
        (-12, [I_ITEM], False),
    ],
)
def test_not_applied(sanction_max, norms, has_aggravating):
    assert part1_limit_months(sanction_max, norms, has_aggravating=has_aggravating) is None


def test_marked_for_legal_review():
    assert NEEDS_LEGAL_REVIEW is True


def test_part3_life_or_death_in_sanction_excludes_part1():
    limit = part1_limit_months(
        240, [I_ITEM], has_aggravating=False, sanction_has_life_or_death=True
    )
    assert limit is None


def test_part1_applies_when_sanction_has_no_life_or_death():
    limit = part1_limit_months(
        240, [I_ITEM], has_aggravating=False, sanction_has_life_or_death=False
    )
    assert limit == 160


@pytest.mark.parametrize(("maximum", "expected"), [(120, 80), (60, 40), (52, 34), (1, 0)])
def test_chapter40_caps_at_two_thirds_rounded_down(maximum, expected):
    assert procedure_maximum(maximum, ProcedureKind.CHAPTER_40) == expected


@pytest.mark.parametrize(("maximum", "expected"), [(120, 60), (15, 7), (1, 0)])
def test_art226_9_caps_at_half_rounded_down(maximum, expected):
    # 15 / 2 = 7.5: 8 months would already exceed one half.
    assert procedure_maximum(maximum, ProcedureKind.ART_226_9) == expected


def test_general_procedure_keeps_the_maximum():
    assert procedure_maximum(60, ProcedureKind.GENERAL) == 60


def test_unknown_procedure_has_no_limit():
    assert procedure_maximum(60, ProcedureKind.UNKNOWN) is None


@pytest.mark.parametrize("maximum", [0, -1])
def test_non_positive_maximum_is_a_caller_error(maximum):
    with pytest.raises(ValueError, match="positive"):
        procedure_maximum(maximum, ProcedureKind.CHAPTER_40)


def _part5(**overrides):
    values = {
        "procedure": ProcedureKind.CHAPTER_40,
        "imposed_months": 40,
        "most_severe_max_months": 60,
        "imposed_most_severe_kind": True,
    }
    values.update(overrides)
    return check_procedure_term(**values)


def test_part5_within_limit_is_ok_and_carries_rule_basis():
    result = _part5()
    assert result.status is CheckStatus.OK
    assert "40" in result.explanation
    assert "ч. 5 ст. 62" in result.explanation
    assert (result.norm, result.source, result.rule_key) == (
        NORM_PART5,
        SOURCE_PART5,
        RULE_KEY_PART5,
    )
    assert result.needs_legal_review is True


def test_part5_above_limit_is_possible_violation():
    result = _part5(imposed_months=41)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "двух третей" in result.explanation


def test_part5_art226_9_uses_one_half():
    result = _part5(procedure=ProcedureKind.ART_226_9, imposed_months=31)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "половины" in result.explanation


def test_part5_general_procedure_does_not_apply():
    result = _part5(procedure=ProcedureKind.GENERAL, imposed_months=60)
    assert result.status is CheckStatus.OK
    assert "не применяется" in result.explanation


def test_part5_unknown_procedure_is_insufficient_data():
    assert _part5(procedure=ProcedureKind.UNKNOWN).status is CheckStatus.INSUFFICIENT_DATA


def test_part5_milder_kind_is_not_checked():
    assert _part5(imposed_most_severe_kind=False).status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize(
    "overrides",
    [
        {"imposed_months": None},
        {"imposed_months": 0},
        {"most_severe_max_months": None},
        {"most_severe_max_months": 0},
    ],
)
def test_part5_missing_numbers_are_insufficient_data(overrides):
    assert _part5(**overrides).status is CheckStatus.INSUFFICIENT_DATA
