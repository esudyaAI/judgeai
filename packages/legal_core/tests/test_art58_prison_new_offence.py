# Domain test — новое преступление во время отбывания наказания в тюрьме: ч. 2 ст. 58 УК РФ с
# разъяснением Пленума ВС РФ от 29.05.2014 N 9 (ред. от 26.11.2024 N 36), п. 7.
from dataclasses import replace

import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art58_prison import (
    NEEDS_LEGAL_REVIEW,
    NEW_OFFENCE_NORM,
    NEW_OFFENCE_RULE_KEY,
    NEW_OFFENCE_SOURCE,
    DraftCumulativePrison,
    PrisonNewOffenceFacts,
    check_new_offence_in_prison,
)

OK = CheckStatus.OK
BAD = CheckStatus.POSSIBLE_VIOLATION
UNKNOWN = CheckStatus.INSUFFICIENT_DATA

IN_PRISON = PrisonNewOffenceFacts(
    offence_while_in_prison=True, unserved_prison_months=18, life_imprisonment=False
)
PROPER = DraftCumulativePrison(
    cumulative_sentences=True, prison_months=18, remaining_regime_stated=True
)


def _check(facts=IN_PRISON, draft=PROPER):
    return check_new_offence_in_prison(facts, draft)


def test_prison_term_equal_to_unserved_part_with_regime_is_ok():
    result = _check()
    assert result.status is OK
    assert result.norm == NEW_OFFENCE_NORM and result.source == NEW_OFFENCE_SOURCE
    assert result.rule_key == NEW_OFFENCE_RULE_KEY
    assert result.needs_legal_review is NEEDS_LEGAL_REVIEW is True


def test_prison_term_above_unserved_part_is_ok():
    assert _check(draft=replace(PROPER, prison_months=30)).status is OK


def test_prison_term_below_unserved_part_is_flagged():
    result = _check(draft=replace(PROPER, prison_months=17))
    assert result.status is BAD
    assert "неотбытой части" in result.explanation


def test_no_prison_part_at_all_is_flagged():
    result = _check(draft=replace(PROPER, prison_months=0))
    assert result.status is BAD


def test_not_cumulative_sentences_is_flagged():
    result = _check(draft=replace(PROPER, cumulative_sentences=False))
    assert result.status is BAD
    assert "совокупности приговоров" in result.explanation


def test_remaining_regime_missing_is_flagged():
    result = _check(draft=replace(PROPER, remaining_regime_stated=False))
    assert result.status is BAD
    assert "оставшейся части" in result.explanation


def test_offence_outside_prison_is_not_this_rule():
    facts = replace(IN_PRISON, offence_while_in_prison=False, unserved_prison_months=None)
    draft = DraftCumulativePrison(None, None, None)
    assert _check(facts, draft).status is OK


@pytest.mark.parametrize(
    ("facts", "draft"),
    [
        (replace(IN_PRISON, offence_while_in_prison=None), PROPER),
        (replace(IN_PRISON, unserved_prison_months=None), PROPER),
        (IN_PRISON, replace(PROPER, cumulative_sentences=None)),
        (IN_PRISON, replace(PROPER, prison_months=None)),
        (IN_PRISON, replace(PROPER, remaining_regime_stated=None)),
        (replace(IN_PRISON, life_imprisonment=True), PROPER),
    ],
    ids=[
        "place-unknown",
        "unserved-unknown",
        "cumulation-unknown",
        "prison-term-unknown",
        "regime-unknown",
        "life",
    ],
)
def test_unknown_facts_are_insufficient_data(facts, draft):
    assert _check(facts, draft).status is UNKNOWN


def test_known_violation_is_reported_before_missing_later_facts():
    draft = DraftCumulativePrison(
        cumulative_sentences=False, prison_months=None, remaining_regime_stated=None
    )
    assert _check(draft=draft).status is BAD


def test_negative_months_are_rejected():
    with pytest.raises(ValueError):
        PrisonNewOffenceFacts(True, -1, False)
    with pytest.raises(ValueError):
        DraftCumulativePrison(True, -1, True)
