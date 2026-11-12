# Domain test — ч. 3 и ч. 4 ст. 70 УК РФ (совокупность приговоров, лишение свободы).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art70 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    RULE_KEY,
    SOURCE,
    DraftCumulativeSentence,
    SentencesCumulationFacts,
    check_cumulative_sentences,
    cumulative_maximum_months,
)

ORDINARY = SentencesCumulationFacts(new_sentence_months=36, unserved_months=24, art56_part5=False)


def _draft(months, *, by_cumulation=True, life=False):
    return DraftCumulativeSentence(
        by_cumulation=by_cumulation, final_months=months, life_imprisonment=life
    )


def test_result_names_rule_norm_and_source():
    result = check_cumulative_sentences(ORDINARY, _draft(48))
    assert result.rule_key == RULE_KEY == "art70.cumulative_sentences"
    assert result.norm == NORM
    assert result.source == SOURCE
    assert result.needs_legal_review is NEEDS_LEGAL_REVIEW is True
    assert "0243481c" in SOURCE


@pytest.mark.parametrize(("part5", "expected"), [(False, 360), (True, 420), (None, None)])
def test_maximum_is_thirty_years_or_thirty_five_under_part5_of_art56(part5, expected):
    assert cumulative_maximum_months(part5) == expected


def test_not_by_cumulation_of_sentences_is_not_this_rule():
    result = check_cumulative_sentences(ORDINARY, _draft(None, by_cumulation=False))
    assert result.status is CheckStatus.OK


def test_unknown_cumulation_is_insufficient_data():
    result = check_cumulative_sentences(ORDINARY, _draft(48, by_cumulation=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_final_term_greater_than_both_and_within_limit_is_ok():
    result = check_cumulative_sentences(ORDINARY, _draft(48))
    assert result.status is CheckStatus.OK


@pytest.mark.parametrize("final", [36, 30])
def test_final_not_greater_than_new_sentence_is_flagged(final):
    result = check_cumulative_sentences(ORDINARY, _draft(final))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 4 ст. 70" in result.explanation
    assert "последнему приговору" in result.explanation


def test_final_not_greater_than_unserved_part_is_flagged():
    facts = SentencesCumulationFacts(new_sentence_months=12, unserved_months=40, art56_part5=False)
    result = check_cumulative_sentences(facts, _draft(40))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "неотбытой части" in result.explanation


def test_both_part4_violations_are_listed_together():
    facts = SentencesCumulationFacts(new_sentence_months=30, unserved_months=30, art56_part5=False)
    result = check_cumulative_sentences(facts, _draft(30))
    assert "последнему приговору" in result.explanation
    assert "неотбытой части" in result.explanation


def test_above_thirty_years_is_flagged_outside_part5():
    facts = SentencesCumulationFacts(new_sentence_months=300, unserved_months=72, art56_part5=False)
    result = check_cumulative_sentences(facts, _draft(361))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 3 ст. 70" in result.explanation


def test_exactly_thirty_years_is_within_the_limit():
    facts = SentencesCumulationFacts(new_sentence_months=300, unserved_months=72, art56_part5=False)
    assert check_cumulative_sentences(facts, _draft(360)).status is CheckStatus.OK


def test_part5_of_art56_raises_the_limit_to_thirty_five_years():
    facts = SentencesCumulationFacts(new_sentence_months=300, unserved_months=72, art56_part5=True)
    assert check_cumulative_sentences(facts, _draft(420)).status is CheckStatus.OK
    assert check_cumulative_sentences(facts, _draft(421)).status is CheckStatus.POSSIBLE_VIOLATION


def test_above_thirty_years_with_unknown_part5_is_insufficient_data():
    facts = SentencesCumulationFacts(new_sentence_months=300, unserved_months=72, art56_part5=None)
    result = check_cumulative_sentences(facts, _draft(400))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "ч. 5 ст. 56" in result.explanation


def test_above_thirty_five_years_is_flagged_even_with_unknown_part5():
    facts = SentencesCumulationFacts(new_sentence_months=300, unserved_months=72, art56_part5=None)
    result = check_cumulative_sentences(facts, _draft(421))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_within_thirty_years_does_not_need_part5():
    facts = SentencesCumulationFacts(new_sentence_months=36, unserved_months=24, art56_part5=None)
    assert check_cumulative_sentences(facts, _draft(48)).status is CheckStatus.OK


@pytest.mark.parametrize(
    "facts",
    [
        SentencesCumulationFacts(new_sentence_months=None, unserved_months=24, art56_part5=False),
        SentencesCumulationFacts(new_sentence_months=36, unserved_months=None, art56_part5=False),
    ],
)
def test_unknown_term_to_compare_is_insufficient_data(facts):
    result = check_cumulative_sentences(facts, _draft(48))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_known_violation_is_reported_even_if_other_facts_are_unknown():
    facts = SentencesCumulationFacts(new_sentence_months=None, unserved_months=50, art56_part5=None)
    result = check_cumulative_sentences(facts, _draft(50))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_unknown_final_term_is_insufficient_data():
    result = check_cumulative_sentences(ORDINARY, _draft(None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_life_imprisonment_is_not_measured_by_these_limits():
    result = check_cumulative_sentences(ORDINARY, _draft(None, life=True))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "пожизненн" in result.explanation


@pytest.mark.parametrize(
    ("facts", "draft"),
    [
        (SentencesCumulationFacts(-1, 24, False), DraftCumulativeSentence(True, 48)),
        (SentencesCumulationFacts(36, -1, False), DraftCumulativeSentence(True, 48)),
        (ORDINARY, DraftCumulativeSentence(True, -1)),
    ],
)
def test_negative_terms_are_rejected(facts, draft):
    with pytest.raises(ValueError):
        check_cumulative_sentences(facts, draft)
