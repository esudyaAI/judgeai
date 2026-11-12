"""T4.14: ч. 1.1 ст. 63 УК РФ — intoxication recognized as an aggravating circumstance."""

import pytest

from legal_core import catalog
from legal_core.checks import CheckStatus
from legal_core.rules import art63
from legal_core.rules.art63 import IntoxicationFacts


def facts(recognized=True, established=True, element=False, motives=True):
    return IntoxicationFacts(
        recognized_in_draft=recognized,
        established=established,
        offence_element=element,
        motives_given=motives,
    )


def check(value):
    return art63.check_intoxication_aggravation(value)


def test_unknown_draft_position_is_insufficient():
    result = check(facts(recognized=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "не установлено" in result.explanation.lower()


def test_not_recognized_is_ok_because_it_is_the_courts_discretion():
    # «может признать» — non-recognition is not a finding, whatever the other facts are.
    result = check(facts(recognized=False, established=None, element=True, motives=False))
    assert result.status is CheckStatus.OK
    assert "право суда" in result.explanation


def test_recognized_with_motives_established_and_not_an_element_is_ok():
    result = check(facts())
    assert result.status is CheckStatus.OK
    assert "мотив" in result.explanation


def test_intoxication_as_an_element_of_the_offence_is_not_counted_again():
    result = check(facts(element=True))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 2 ст. 63" in result.explanation
    assert "признак" in result.explanation


def test_recognized_without_motives_is_a_possible_violation():
    result = check(facts(motives=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "мотив" in result.explanation
    assert "п. 31" in result.explanation


def test_recognized_although_intoxication_not_established_is_a_possible_violation():
    result = check(facts(established=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "не установлено" in result.explanation


def test_all_known_violations_are_reported_together():
    result = check(facts(established=False, element=True, motives=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    for fragment in ("признак", "не установлено", "мотив"):
        assert fragment in result.explanation


def test_known_violation_is_reported_even_if_other_facts_are_unknown():
    result = check(facts(established=None, element=None, motives=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "мотив" in result.explanation


@pytest.mark.parametrize(
    ("changes", "missing"),
    [
        ({"established": None}, "установлено ли состояние опьянения"),
        ({"element": None}, "признаком состава"),
        ({"motives": None}, "мотивы"),
    ],
)
def test_unknown_fact_without_violation_is_insufficient(changes, missing):
    result = check(facts(**changes))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert missing in result.explanation


def test_result_carries_rule_key_norm_and_review_flag():
    result = check(facts())
    assert result.rule_key == art63.INTOXICATION_RULE_KEY == "art63.intoxication_aggravating"
    assert result.norm == art63.INTOXICATION_NORM
    assert "ч. 1.1" in result.norm
    assert result.needs_legal_review is True
    assert "pravo.gov.ru" in result.source
    assert "N 58" in result.source


def test_rule_is_in_catalog_with_article_63():
    descriptor = next(rule for rule in catalog.RULES if rule.key == art63.INTOXICATION_RULE_KEY)
    assert descriptor.title == art63.INTOXICATION_NORM
    assert catalog.NormLocator(catalog.CRIMINAL_CODE, "article.63") in descriptor.norms
    assert descriptor.needs_legal_review is True
    assert "признаком" in descriptor.not_modelled


def test_recidivism_rule_no_longer_claims_part_1_1_is_unchecked():
    descriptor = next(rule for rule in catalog.RULES if rule.key == art63.RULE_KEY)
    assert "Ч. 1.1" not in descriptor.not_modelled
    assert "art63.intoxication_aggravating" in descriptor.not_modelled
