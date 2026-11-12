"""T4.19: ч. 4 ст. 69 и ч. 5 ст. 70 УК РФ — дополнительные наказания при совокупности."""

import pytest

from legal_core.checks import CheckStatus
from legal_core.rules import art69
from legal_core.rules.art69 import (
    AdditionalPunishment,
    CumulationBasis,
    CumulationMethod,
    DraftAdditionalCumulation,
    check_additional_punishments,
)

BAN = "лишение права занимать определённые должности"


def _ban(amount, maximum=60):
    return AdditionalPunishment(BAN, amount, maximum)


def _draft(*additional, **changes):
    values = {
        "by_cumulation": True,
        "basis": CumulationBasis.OFFENCES,
        "method": CumulationMethod.PARTIAL_ADDITION,
        "additional": additional or (_ban(36),),
    }
    values.update(changes)
    return DraftAdditionalCumulation(**values)


def test_result_carries_its_own_rule_key_and_source():
    result = check_additional_punishments(_draft())
    assert result.rule_key == art69.ADDITIONAL_RULE_KEY == "art69.additional_punishments"
    assert result.norm == art69.ADDITIONAL_NORM
    assert "ст. 69" in result.source and "ст. 70" in result.source
    assert "sha256" in result.source
    assert result.needs_legal_review is True


def test_not_by_cumulation_is_ok_and_unknown_is_insufficient():
    assert check_additional_punishments(_draft(by_cumulation=False)).status is CheckStatus.OK
    unknown = check_additional_punishments(_draft(by_cumulation=None))
    assert unknown.status is CheckStatus.INSUFFICIENT_DATA


def test_no_additional_punishment_is_ok_because_joining_is_the_courts_right():
    result = check_additional_punishments(_draft(additional=()))
    assert result.status is CheckStatus.OK
    assert "не назначены" in result.explanation


@pytest.mark.parametrize(
    ("basis", "method"),
    [
        (CumulationBasis.OFFENCES, CumulationMethod.PARTIAL_ADDITION),
        (CumulationBasis.OFFENCES, CumulationMethod.FULL_ADDITION),
        (CumulationBasis.SENTENCES, None),
        (None, CumulationMethod.FULL_ADDITION),
    ],
)
def test_maximum_of_the_general_part_is_inclusive(basis, method):
    result = check_additional_punishments(_draft(_ban(60), basis=basis, method=method))
    assert result.status is CheckStatus.OK


def test_offences_cumulation_above_maximum_is_a_violation_of_part4_art69():
    result = check_additional_punishments(_draft(_ban(61)))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert BAN in result.explanation
    assert "61" in result.explanation and "60" in result.explanation
    assert "ч. 4 ст. 69" in result.explanation
    assert "ч. 5 ст. 70" not in result.explanation


def test_sentences_cumulation_applies_part4_art69_through_part5_art70_for_any_method():
    for method in (None, CumulationMethod.ABSORPTION):
        result = check_additional_punishments(
            _draft(_ban(61), basis=CumulationBasis.SENTENCES, method=method)
        )
        assert result.status is CheckStatus.POSSIBLE_VIOLATION
        assert "ч. 5 ст. 70" in result.explanation and "ч. 4 ст. 69" in result.explanation


def test_absorption_under_art69_is_outside_the_limit_of_part4():
    for basis in (CumulationBasis.OFFENCES, None):
        result = check_additional_punishments(
            _draft(_ban(61), basis=basis, method=CumulationMethod.ABSORPTION)
        )
        assert result.status is CheckStatus.OK
        assert "поглощ" in result.explanation


def test_unknown_method_matters_only_when_the_maximum_is_exceeded():
    within = check_additional_punishments(_draft(_ban(60), method=None))
    assert within.status is CheckStatus.OK
    for basis in (CumulationBasis.OFFENCES, None):
        above = check_additional_punishments(_draft(_ban(61), basis=basis, method=None))
        assert above.status is CheckStatus.INSUFFICIENT_DATA
        assert "способ" in above.explanation


def test_unknown_amount_or_maximum_is_insufficient_data():
    for punishment in (_ban(None), _ban(36, None)):
        result = check_additional_punishments(_draft(punishment))
        assert result.status is CheckStatus.INSUFFICIENT_DATA
        assert BAN in result.explanation


def test_known_violation_is_reported_even_if_another_punishment_is_not_established():
    fine = AdditionalPunishment("штраф", 6_000_000, 5_000_000)
    result = check_additional_punishments(_draft(_ban(None), fine))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "штраф" in result.explanation and BAN not in result.explanation


def test_every_exceeding_punishment_is_listed():
    fine = AdditionalPunishment("штраф", 6_000_000, 5_000_000)
    result = check_additional_punishments(_draft(_ban(72), fine))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "штраф" in result.explanation and BAN in result.explanation


@pytest.mark.parametrize(
    "punishment",
    [_ban(-1), _ban(12, 0), _ban(12, -5), AdditionalPunishment(" ", 12, 60)],
)
def test_invalid_input_is_an_error(punishment):
    with pytest.raises(ValueError):
        check_additional_punishments(_draft(punishment))
