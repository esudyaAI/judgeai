# Domain test — T28: distribution of terms imposed in comparable precedents.
import pytest

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification
from legal_core.rules.practice_comparison import MIN_PRECEDENTS, Position, compare_with_practice

THEFT = Qualification("158", 2, "в")


def card(months=None, *, conditional=False, general=(), kind=PunishmentKind.IMPRISONMENT):
    term = None
    if months is not None:
        unit = MeasureUnit.MONTHS if kind is PunishmentKind.IMPRISONMENT else MeasureUnit.RUBLES
        term = PunishmentTerm(kind, months, unit)
    return PrecedentCard(
        episodes=(PrecedentEpisode(THEFT, term),),
        mitigating=frozenset(),
        aggravating=frozenset(),
        recidivism=None,
        applied_general=frozenset(general),
        final=None,
        conditional=conditional,
        fabula="",
    )


def test_empty_practice_has_no_statistics():
    result = compare_with_practice([], draft_months=12)
    assert result.total == 0 and result.with_term == 0
    assert result.median_months is None and result.position is None
    assert result.enough_data is False


def test_quartiles_by_linear_interpolation():
    result = compare_with_practice([card(m) for m in (6, 12, 18, 24, 36)], draft_months=None)
    assert (result.min_months, result.max_months) == (6, 36)
    assert (result.p25_months, result.median_months, result.p75_months) == (12, 18, 24)
    assert result.with_term == 5 and result.enough_data is True


def test_even_count_median_is_the_mean_of_the_middle_pair():
    result = compare_with_practice([card(m) for m in (10, 20, 30, 40)], draft_months=None)
    assert result.median_months == 25
    assert (result.p25_months, result.p75_months) == (17.5, 32.5)


@pytest.mark.parametrize(
    ("draft", "position", "rank"),
    [
        (4, Position.BELOW, 0.0),
        (18, Position.WITHIN, 50.0),
        (12, Position.WITHIN, 30.0),  # the boundary of the interquartile range is inside
        (40, Position.ABOVE, 100.0),
    ],
)
def test_draft_position(draft, position, rank):
    result = compare_with_practice([card(m) for m in (6, 12, 18, 24, 36)], draft_months=draft)
    assert result.position is position
    assert result.draft_percentile == rank


def test_no_position_on_too_few_precedents():
    few = [card(m) for m in range(1, MIN_PRECEDENTS)]
    result = compare_with_practice(few, draft_months=3)
    assert result.enough_data is False and result.position is None
    assert result.median_months is not None  # statistics are shown, a verdict on them is not


def test_terms_unknown_or_not_imprisonment_are_counted_but_not_in_the_distribution():
    cards = [card(12), card(None), card(50_000, kind=PunishmentKind.FINE)]
    result = compare_with_practice(cards, draft_months=None)
    assert result.total == 3 and result.with_term == 1


def test_shares_of_conditional_and_general_part_rules():
    cards = [
        card(12, conditional=True, general={"73"}),
        card(12, general={"64"}),
        card(24),
        card(None, conditional=True, general={"73", "62.1"}),
    ]
    result = compare_with_practice(cards, draft_months=None)
    assert result.conditional_share == 0.5
    assert result.art64_share == 0.25
    assert result.art73_share == 0.5


def test_fractional_months_from_day_terms_are_not_truncated():
    from dataclasses import replace

    from legal_core.entities import MeasureUnit, PunishmentTerm

    value = card(1)
    days = replace(value, final=PunishmentTerm(PunishmentKind.IMPRISONMENT, 15, MeasureUnit.DAYS))
    result = compare_with_practice([days] * 5, draft_months=0.5)
    assert result.min_months == result.max_months == result.median_months == 0.5
    assert result.draft_months == 0.5 and result.draft_percentile == 50
