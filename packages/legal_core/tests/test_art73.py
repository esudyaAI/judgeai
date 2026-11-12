# Domain test — п. «в» ч. 1 ст. 73 УК РФ (запрет условного осуждения при опасном и особо
# опасном рецидиве).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art73 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    SOURCE,
    check_conditional_sentence_recidivism_bar,
)

BARRED = [Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS]
NOT_BARRED = [Recidivism.NONE, Recidivism.SIMPLE]


def _check(**overrides):
    params = {"recidivism": Recidivism.SIMPLE, "conditional_in_draft": True}
    params.update(overrides)
    return check_conditional_sentence_recidivism_bar(**params)


def test_result_is_marked_for_legal_review_with_source():
    result = _check()
    assert NEEDS_LEGAL_REVIEW is True
    assert result.needs_legal_review is True
    assert result.norm == NORM
    assert result.source == SOURCE
    assert "п. «в» ч. 1 ст. 73" in NORM
    assert "pravo.gov.ru" in SOURCE and "172-ФЗ" in SOURCE
    assert "N 58" in SOURCE and "п. 62" in SOURCE


@pytest.mark.parametrize("kind", BARRED)
def test_conditional_sentence_with_dangerous_recidivism_is_flagged(kind):
    result = _check(recidivism=kind, conditional_in_draft=True)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «в» ч. 1 ст. 73" in result.explanation
    assert "опасн" in result.explanation


def test_flag_names_the_kind_of_recidivism():
    especially = _check(recidivism=Recidivism.ESPECIALLY_DANGEROUS)
    dangerous = _check(recidivism=Recidivism.DANGEROUS)
    assert "осуждённого особо опасный рецидив" in especially.explanation
    assert "осуждённого опасный рецидив" in dangerous.explanation


@pytest.mark.parametrize("kind", NOT_BARRED)
def test_conditional_sentence_without_dangerous_recidivism_is_ok(kind):
    result = _check(recidivism=kind, conditional_in_draft=True)
    assert result.status is CheckStatus.OK
    # Only п. «в» is checked; the other bars of ч. 1 are left to the judge and said so.
    assert "«а»" in result.explanation and "«б»" in result.explanation


@pytest.mark.parametrize("kind", [*BARRED, *NOT_BARRED, Recidivism.UNKNOWN])
def test_real_punishment_is_never_flagged(kind):
    result = _check(recidivism=kind, conditional_in_draft=False)
    assert result.status is CheckStatus.OK
    assert "не назначено" in result.explanation


def test_unknown_recidivism_with_conditional_sentence_is_insufficient_data():
    result = _check(recidivism=Recidivism.UNKNOWN, conditional_in_draft=True)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "Вид рецидива" in result.explanation


@pytest.mark.parametrize("kind", [*BARRED, *NOT_BARRED, Recidivism.UNKNOWN])
def test_not_extracted_draft_position_is_insufficient_data(kind):
    result = _check(recidivism=kind, conditional_in_draft=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "условн" in result.explanation
