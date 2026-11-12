"""T4.12: general limits of ч. 1 ст. 73 УК РФ — punishment kinds and imprisonment up to 8 years."""

import pytest

from legal_core import catalog
from legal_core.checks import CheckStatus
from legal_core.entities import PunishmentKind
from legal_core.rules import art73

ALLOWED = [
    PunishmentKind.CORRECTIONAL_WORKS,
    PunishmentKind.MILITARY_SERVICE_RESTRICTION,
    PunishmentKind.DISCIPLINARY_MILITARY_UNIT,
]
BARRED = [
    PunishmentKind.FINE,
    PunishmentKind.DEPRIVATION_OF_RIGHT,
    PunishmentKind.COMPULSORY_WORKS,
    PunishmentKind.RESTRICTION_OF_FREEDOM,
    PunishmentKind.FORCED_LABOUR,
    PunishmentKind.ARREST,
    PunishmentKind.LIFE_IMPRISONMENT,
    PunishmentKind.DEATH_PENALTY,
]


def check(kind, months=None, conditional=True):
    return art73.check_conditional_sentence_limits(
        final_kind=kind, final_months=months, conditional_in_draft=conditional
    )


def test_not_conditional_is_ok():
    result = check(PunishmentKind.FINE, conditional=False)
    assert result.status is CheckStatus.OK


def test_unknown_conditional_is_insufficient():
    assert check(PunishmentKind.IMPRISONMENT, 12, None).status is CheckStatus.INSUFFICIENT_DATA


def test_unknown_kind_is_insufficient():
    assert check(None, 12).status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize("kind", ALLOWED)
def test_allowed_non_custodial_kinds_are_ok(kind):
    assert check(kind).status is CheckStatus.OK


@pytest.mark.parametrize("kind", BARRED)
def test_other_kinds_cannot_be_conditional(kind):
    result = check(kind, 12)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 1 ст. 73" in result.explanation


@pytest.mark.parametrize("months", [1, 60, 95, 96])
def test_imprisonment_up_to_eight_years_is_ok(months):
    assert check(PunishmentKind.IMPRISONMENT, months).status is CheckStatus.OK


def test_imprisonment_over_eight_years_is_violation():
    result = check(PunishmentKind.IMPRISONMENT, 97)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "восьми лет" in result.explanation


def test_imprisonment_without_term_is_insufficient():
    result = check(PunishmentKind.IMPRISONMENT, None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_negative_term_is_rejected():
    with pytest.raises(ValueError):
        check(PunishmentKind.IMPRISONMENT, -1)


def test_result_names_its_rule_and_needs_review():
    result = check(PunishmentKind.IMPRISONMENT, 12)
    assert result.rule_key == art73.LIMITS_RULE_KEY == "art73.conditional_limits"
    assert result.needs_legal_review is True
    assert catalog.rule(art73.LIMITS_RULE_KEY).title == art73.LIMITS_NORM


def test_conditional_ban_no_longer_claims_limits_unchecked():
    rule = catalog.rule(art73.RULE_KEY)
    assert "общие пределы" not in rule.not_modelled
