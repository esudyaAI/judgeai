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
