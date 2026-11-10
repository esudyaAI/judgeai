"""T4.13: пп. «а», «а1» ч. 1 ст. 73 УК РФ — offences for which a conditional sentence is barred."""

import pytest

from legal_core import catalog
from legal_core.checks import CheckStatus
from legal_core.rules import art73
from legal_core.rules.art73 import ListedOffence


def offence(child=False, a1=False, article="ч. 1 ст. 158 УК РФ"):
    return ListedOffence(article=article, child_sexual_inviolability=child, in_a1_list=a1)


def check(offences, conditional=True):
    return art73.check_conditional_sentence_offence_bar(
        offences=offences, conditional_in_draft=conditional
    )


def test_not_conditional_is_ok_whatever_the_offences():
    result = check([offence(child=True)], conditional=False)
    assert result.status is CheckStatus.OK
    assert "не назначено" in result.explanation


def test_unknown_conditional_is_insufficient():
    assert check([offence()], conditional=None).status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize("offences", [None, []])
def test_unknown_or_empty_offences_are_insufficient(offences):
    result = check(offences)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "не установлен" in result.explanation.lower()


def test_child_sexual_inviolability_bars_conditional_sentence():
    result = check([offence(child=True, article="п. «б» ч. 4 ст. 132 УК РФ")])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «а» ч. 1 ст. 73" in result.explanation
    assert "п. «б» ч. 4 ст. 132 УК РФ" in result.explanation


def test_a1_list_bars_conditional_sentence():
    result = check([offence(a1=True, article="ч. 1 ст. 205.2 УК РФ")])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «а1» ч. 1 ст. 73" in result.explanation
    assert "ч. 1 ст. 205.2 УК РФ" in result.explanation


def test_one_barred_offence_among_several_is_enough():
    # Пленум № 58, п. 62: the conditional decision is taken once, for the final punishment.
    result = check([offence(), offence(a1=None), offence(child=True, a1=None)])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_both_points_are_named_when_both_apply():
    result = check([offence(child=True, article="ст. 134"), offence(a1=True, article="ст. 360")])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «а»" in result.explanation and "п. «а1»" in result.explanation


@pytest.mark.parametrize(
    "unknown", [offence(child=None), offence(a1=None), offence(child=None, a1=None)]
)
def test_unknown_membership_without_a_bar_is_insufficient(unknown):
    result = check([offence(), unknown])
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert unknown.article in result.explanation


def test_no_listed_offence_is_ok():
    result = check([offence(), offence(article="ч. 2 ст. 159 УК РФ")])
    assert result.status is CheckStatus.OK
    assert "пп. «а», «а1»" in result.explanation


def test_result_carries_rule_key_source_and_review_flag():
    result = check([offence()])
    assert result.rule_key == art73.OFFENCE_LIST_RULE_KEY == "art73.offence_list_bar"
    assert result.norm == art73.OFFENCE_LIST_NORM
    assert "pravo.gov.ru" in result.source and "420-ФЗ" in result.source
    assert result.needs_legal_review is True


def test_listed_offence_requires_an_article():
    with pytest.raises(ValueError):
        ListedOffence(article=" ", child_sexual_inviolability=False, in_a1_list=False)


def test_rule_is_in_the_catalog_and_says_lists_are_passed_by_the_caller():
    item = catalog.rule("art73.offence_list_bar")
    assert item.title == art73.OFFENCE_LIST_NORM
    assert "вызывающий" in item.not_modelled
    assert "пп. «а», «а1»" not in catalog.rule("art73.conditional_ban").not_modelled.lower()
