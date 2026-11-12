# Domain test — п. «б» ч. 1 ст. 73 УК РФ (запрет условного осуждения за тяжкое или особо тяжкое
# преступление в испытательный срок или в неотбытую часть наказания при УДО).

from datetime import date

import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import Category
from legal_core.rules.art73 import (
    SUPERVISION_NORM,
    SUPERVISION_RULE_KEY,
    SUPERVISION_SOURCE,
    PriorSupervision,
    SupervisionKind,
    check_conditional_sentence_during_supervision,
)

START = date(2024, 3, 1)
END = date(2026, 3, 1)
INSIDE = date(2025, 1, 15)


def _period(**overrides) -> PriorSupervision:
    params = {
        "kind": SupervisionKind.PROBATION,
        "started_on": START,
        "ended_on": END,
        "intentional": True,
    }
    params.update(overrides)
    return PriorSupervision(**params)


def _check(**overrides):
    params = {
        "offence_category": Category.GRAVE,
        "offence_date": INSIDE,
        "supervisions": [_period()],
        "conditional_in_draft": True,
    }
    params.update(overrides)
    return check_conditional_sentence_during_supervision(**params)


def test_result_is_marked_for_legal_review_with_source_and_key():
    result = _check()
    assert result.needs_legal_review is True
    assert result.norm == SUPERVISION_NORM
    assert result.source == SUPERVISION_SOURCE
    assert result.rule_key == SUPERVISION_RULE_KEY == "art73.offence_during_supervision"
    assert "п. «б» ч. 1 ст. 73" in SUPERVISION_NORM
    assert "pravo.gov.ru" in SUPERVISION_SOURCE and "172-ФЗ" in SUPERVISION_SOURCE


@pytest.mark.parametrize("category", [Category.GRAVE, Category.ESPECIALLY_GRAVE])
@pytest.mark.parametrize("kind", list(SupervisionKind))
def test_grave_offence_during_supervision_is_flagged(category, kind):
    result = _check(offence_category=category, supervisions=[_period(kind=kind)])
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «б» ч. 1 ст. 73" in result.explanation


def test_flag_names_probation_and_parole_differently():
    probation = _check(supervisions=[_period(kind=SupervisionKind.PROBATION)])
    parole = _check(supervisions=[_period(kind=SupervisionKind.PAROLE)])
    assert "испытательного срока" in probation.explanation
    assert "условно-досрочном" in parole.explanation


@pytest.mark.parametrize("category", [Category.SMALL, Category.MEDIUM])
def test_lesser_offence_is_outside_the_bar(category):
    result = _check(offence_category=category, supervisions=None, offence_date=None)
    assert result.status is CheckStatus.OK


def test_real_punishment_is_never_flagged():
    assert _check(conditional_in_draft=False).status is CheckStatus.OK


@pytest.mark.parametrize(
    "overrides",
    [
        {"conditional_in_draft": None},
        {"offence_category": None},
        {"supervisions": None},
        {"offence_date": None},
        {"supervisions": [_period(started_on=None)]},
        {"supervisions": [_period(ended_on=None)]},
        {"supervisions": [_period(intentional=None)]},
    ],
)
def test_unknown_facts_are_insufficient_data(overrides):
    assert _check(**overrides).status is CheckStatus.INSUFFICIENT_DATA


def test_no_prior_supervision_is_ok():
    assert _check(supervisions=[]).status is CheckStatus.OK


def test_no_supervision_needs_no_offence_date():
    assert _check(supervisions=[], offence_date=None).status is CheckStatus.OK


@pytest.mark.parametrize("offence", [date(2024, 2, 29), date(2026, 3, 2)])
def test_offence_outside_the_period_is_ok(offence):
    assert _check(offence_date=offence).status is CheckStatus.OK


@pytest.mark.parametrize("offence", [START, END])
def test_offence_on_the_boundary_day_is_insufficient_data(offence):
    assert _check(offence_date=offence).status is CheckStatus.INSUFFICIENT_DATA


def test_period_that_ended_before_the_offence_needs_no_start_date():
    period = _period(started_on=None, ended_on=date(2024, 1, 1))
    assert _check(supervisions=[period]).status is CheckStatus.OK


def test_period_that_starts_after_the_offence_needs_no_end_date():
    period = _period(started_on=date(2025, 6, 1), ended_on=None)
    assert _check(supervisions=[period]).status is CheckStatus.OK


def test_careless_prior_offence_is_outside_the_bar():
    assert _check(supervisions=[_period(intentional=False)]).status is CheckStatus.OK


def test_outside_period_with_unknown_intent_is_ok():
    period = _period(intentional=None, ended_on=date(2024, 6, 1))
    assert _check(supervisions=[period]).status is CheckStatus.OK


def test_violation_outweighs_an_unknown_period():
    periods = [_period(started_on=None), _period()]
    assert _check(supervisions=periods).status is CheckStatus.POSSIBLE_VIOLATION


def test_unknown_period_outweighs_a_clear_one():
    periods = [_period(intentional=False), _period(ended_on=None)]
    assert _check(supervisions=periods).status is CheckStatus.INSUFFICIENT_DATA


def test_reversed_period_is_rejected():
    with pytest.raises(ValueError):
        _period(started_on=END, ended_on=START)
