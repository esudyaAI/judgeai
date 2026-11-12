import pytest

from src.schemas.analysis import Circumstance
from src.services.sentencing import art62_part1_limit, has_art62_part1_mitigation


def c(norm: str) -> Circumstance:
    return Circumstance(name="x", norm=norm)


@pytest.mark.parametrize(
    ("norm", "expected"),
    [
        ("п. «и» ч. 1 ст. 61", True),
        ("п. «к» ч. 1 ст. 61 УК РФ", True),
        ("п. «г», «и» ч. 1 ст. 61", True),
        ("пп. «и», «к» ч.1 ст.61", True),
        ("п. «г» ч. 1 ст. 61", False),
        ("ч. 2 ст. 61", False),
        ("п. «и» ч. 1 ст. 63", False),
        ("п. «к» ч. 1 ст. 610", False),
        ("п. «и» ч. 1 ст. 61.1", False),
        ("", False),
    ],
)
def test_detects_art61_items_i_k(norm, expected):
    assert has_art62_part1_mitigation([c(norm)]) is expected


def test_two_thirds_of_sanction_rounded_down():
    assert art62_part1_limit(60, [c("п. «и» ч. 1 ст. 61")], []) == 40
    # 2/3 of 4 years 4 months (52) = 34.67 -> 34, never 35 (would exceed the statutory cap)
    assert art62_part1_limit(52, [c("п. «к» ч. 1 ст. 61")], []) == 34


def test_not_applied_with_aggravating_or_without_items():
    assert art62_part1_limit(60, [c("п. «и» ч. 1 ст. 61")], [c("п. «а» ч. 1 ст. 63")]) is None
    assert art62_part1_limit(60, [c("ч. 2 ст. 61")], []) is None
    assert art62_part1_limit(0, [c("п. «и» ч. 1 ст. 61")], []) is None


def test_life_or_death_in_sanction_excludes_part1():
    limit = art62_part1_limit(240, [c("п. «и» ч. 1 ст. 61")], [], sanction_has_life_or_death=True)
    assert limit is None
