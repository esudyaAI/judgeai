"""T4.20: ч. 5 ст. 69 УК РФ — преступление до вынесения первого приговора, зачёт отбытого."""

import pytest

from legal_core.checks import CheckStatus
from legal_core.rules import art69
from legal_core.rules.art69 import (
    DraftPriorSentence,
    PriorSentenceFacts,
    check_prior_sentence,
)


def _facts(**changes):
    values = {
        "offence_before_first_sentence": True,
        "first_conditional_in_force": False,
        "served_under_first": True,
    }
    values.update(changes)
    return PriorSentenceFacts(**values)


def _draft(**changes):
    values = {"applies_part5": True, "credits_served": True}
    values.update(changes)
    return DraftPriorSentence(**values)


def test_result_carries_its_own_rule_key_and_source():
    result = check_prior_sentence(_facts(), _draft())
    assert result.rule_key == art69.PRIOR_RULE_KEY == "art69.prior_sentence"
    assert result.norm == art69.PRIOR_NORM
    assert "ч. 5" in result.source and "ст. 69" in result.source
    assert "sha256" in result.source and "№ 58" in result.source
    assert result.needs_legal_review is True


def test_part5_with_credit_of_served_punishment_is_ok():
    result = check_prior_sentence(_facts(), _draft())
    assert result.status is CheckStatus.OK
    assert "ч. 5 ст. 69" in result.explanation


def test_nothing_served_needs_no_credit():
    result = check_prior_sentence(_facts(served_under_first=False), _draft(credits_served=False))
    assert result.status is CheckStatus.OK


def test_served_punishment_not_credited_is_a_violation():
    result = check_prior_sentence(_facts(), _draft(credits_served=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "засчитывается" in result.explanation


@pytest.mark.parametrize(
    ("served", "credits"),
    [(True, None), (None, False), (None, None)],
)
def test_unknown_credit_facts_are_insufficient(served, credits):
    result = check_prior_sentence(_facts(served_under_first=served), _draft(credits_served=credits))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_credit_stated_while_service_unknown_is_ok():
    result = check_prior_sentence(_facts(served_under_first=None), _draft(credits_served=True))
    assert result.status is CheckStatus.OK


def test_part5_for_offence_after_the_first_sentence_is_a_violation():
    result = check_prior_sentence(_facts(offence_before_first_sentence=False), _draft())
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 70" in result.explanation


def test_part5_while_conditional_sentence_is_in_force_is_a_violation():
    result = check_prior_sentence(_facts(first_conditional_in_force=True), _draft())
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "самостоятельно" in result.explanation


def test_all_known_violations_are_listed_together_despite_gaps():
    result = check_prior_sentence(
        _facts(offence_before_first_sentence=False, first_conditional_in_force=True),
        _draft(credits_served=None),
    )
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 70" in result.explanation and "самостоятельно" in result.explanation


@pytest.mark.parametrize(
    "changes",
    [{"offence_before_first_sentence": None}, {"first_conditional_in_force": None}],
)
def test_part5_with_unknown_grounds_is_insufficient(changes):
    result = check_prior_sentence(_facts(**changes), _draft())
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_part5_not_applied_when_it_should_be_is_a_violation():
    result = check_prior_sentence(_facts(), _draft(applies_part5=False, credits_served=None))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 5 ст. 69" in result.explanation


@pytest.mark.parametrize(
    "changes",
    [{"offence_before_first_sentence": False}, {"first_conditional_in_force": True}],
)
def test_part5_not_applied_and_not_required_is_ok(changes):
    result = check_prior_sentence(_facts(**changes), _draft(applies_part5=False))
    assert result.status is CheckStatus.OK


@pytest.mark.parametrize(
    "changes",
    [{"offence_before_first_sentence": None}, {"first_conditional_in_force": None}],
)
def test_part5_not_applied_with_unknown_grounds_is_insufficient(changes):
    result = check_prior_sentence(_facts(**changes), _draft(applies_part5=False))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_unknown_whether_part5_is_applied_is_insufficient():
    result = check_prior_sentence(_facts(), _draft(applies_part5=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
