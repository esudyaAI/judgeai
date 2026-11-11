# Domain test — ч. 2 и ч. 4 ст. 62 УК РФ (досудебное соглашение о сотрудничестве).

import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art62 import (
    AGREEMENT_NORM,
    AGREEMENT_RULE_KEY,
    AGREEMENT_SOURCE,
    NEEDS_LEGAL_REVIEW,
    DraftAgreementTerm,
    PretrialAgreementFacts,
    agreement_maximum,
    check_pretrial_agreement_term,
)

PART2 = PretrialAgreementFacts(
    agreement=True, item_i_mitigation=True, has_aggravating=False, sanction_has_life_or_death=False
)
PART4 = PretrialAgreementFacts(
    agreement=True, item_i_mitigation=None, has_aggravating=None, sanction_has_life_or_death=True
)


def _draft(months=None, base=120, *, life_or_death=False, most_severe=True):
    return DraftAgreementTerm(
        imposed_life_or_death=life_or_death,
        imposed_most_severe_kind=most_severe,
        imposed_months=months,
        limit_base_max_months=base,
    )


def test_result_names_rule_norm_and_source():
    result = check_pretrial_agreement_term(PART2, _draft(60))
    assert result.rule_key == AGREEMENT_RULE_KEY
    assert result.norm == AGREEMENT_NORM
    assert result.source == AGREEMENT_SOURCE
    assert result.needs_legal_review is NEEDS_LEGAL_REVIEW is True
    assert "0243481c" in AGREEMENT_SOURCE


@pytest.mark.parametrize(
    ("base", "has_life", "expected"),
    [(120, False, 60), (121, False, 60), (7, False, 3), (240, True, 160), (100, True, 66)],
)
def test_agreement_maximum_rounds_down(base, has_life, expected):
    assert agreement_maximum(base, sanction_has_life_or_death=has_life) == expected


def test_agreement_maximum_rejects_non_positive_base():
    with pytest.raises(ValueError):
        agreement_maximum(0, sanction_has_life_or_death=False)


def test_no_agreement_does_not_apply():
    facts = PretrialAgreementFacts(False, None, None, None)
    result = check_pretrial_agreement_term(facts, _draft(None, None, life_or_death=None))
    assert result.status is CheckStatus.OK
    assert "не заключалось" in result.explanation


def test_unknown_agreement_is_insufficient_data():
    facts = PretrialAgreementFacts(None, True, False, False)
    assert check_pretrial_agreement_term(facts, _draft(60)).status is CheckStatus.INSUFFICIENT_DATA


def test_part2_within_one_half():
    result = check_pretrial_agreement_term(PART2, _draft(60))
    assert result.status is CheckStatus.OK
    assert "ч. 2 ст. 62" in result.explanation and "60 из 120" in result.explanation


def test_part2_above_one_half_is_possible_violation():
    result = check_pretrial_agreement_term(PART2, _draft(61))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "половины" in result.explanation and "ч. 2 ст. 62" in result.explanation


@pytest.mark.parametrize(
    "facts",
    [
        PretrialAgreementFacts(True, False, False, False),
        PretrialAgreementFacts(True, True, True, False),
        PretrialAgreementFacts(True, False, None, False),
        PretrialAgreementFacts(True, None, True, False),
    ],
)
def test_part2_does_not_apply_without_item_i_or_with_aggravating(facts):
    result = check_pretrial_agreement_term(facts, _draft(100))
    assert result.status is CheckStatus.OK
    assert "ч. 2 ст. 62" in result.explanation and "не применяется" in result.explanation


@pytest.mark.parametrize(
    "facts",
    [
        PretrialAgreementFacts(True, None, False, False),
        PretrialAgreementFacts(True, True, None, False),
        PretrialAgreementFacts(True, True, False, None),
    ],
)
def test_part2_unknown_conditions_are_insufficient_data(facts):
    assert check_pretrial_agreement_term(facts, _draft(100)).status is (
        CheckStatus.INSUFFICIENT_DATA
    )


def test_unknown_sanction_life_or_death_with_imposed_life_is_still_insufficient():
    facts = PretrialAgreementFacts(True, False, False, None)
    result = check_pretrial_agreement_term(facts, _draft(None, None, life_or_death=True))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_part4_within_two_thirds_of_imprisonment():
    result = check_pretrial_agreement_term(PART4, _draft(160, 240))
    assert result.status is CheckStatus.OK
    assert "ч. 4 ст. 62" in result.explanation and "160 из 240" in result.explanation


def test_part4_above_two_thirds_is_possible_violation():
    result = check_pretrial_agreement_term(PART4, _draft(161, 240))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "двух третей" in result.explanation


def test_part4_life_or_death_imposed_is_violation_even_without_numbers():
    result = check_pretrial_agreement_term(PART4, _draft(None, None, life_or_death=True))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "не применяются" in result.explanation


def test_part4_unknown_whether_life_imposed_is_insufficient_data():
    result = check_pretrial_agreement_term(PART4, _draft(100, 240, life_or_death=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_part4_does_not_depend_on_mitigation_or_aggravation():
    facts = PretrialAgreementFacts(True, False, True, True)
    assert check_pretrial_agreement_term(facts, _draft(150, 240)).status is CheckStatus.OK


@pytest.mark.parametrize("facts", [PART2, PART4])
def test_milder_kind_is_not_checked(facts):
    result = check_pretrial_agreement_term(facts, _draft(500, 240, most_severe=False))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "менее строгий" in result.explanation


@pytest.mark.parametrize("facts", [PART2, PART4])
def test_unknown_kind_is_insufficient_data(facts):
    result = check_pretrial_agreement_term(facts, _draft(100, 240, most_severe=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize(("months", "base"), [(None, 120), (60, None)])
@pytest.mark.parametrize("facts", [PART2, PART4])
def test_missing_numbers_are_insufficient_data(facts, months, base):
    assert check_pretrial_agreement_term(facts, _draft(months, base)).status is (
        CheckStatus.INSUFFICIENT_DATA
    )


@pytest.mark.parametrize(("months", "base"), [(-1, 120), (60, 0), (60, -5)])
def test_invalid_numbers_raise(months, base):
    with pytest.raises(ValueError):
        check_pretrial_agreement_term(PART2, _draft(months, base))
