# Domain test — п. «а» ч. 1 и ч. 2 ст. 63 УК РФ (рецидив как отягчающее обстоятельство).
import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art63 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    SOURCE,
    check_recidivism_aggravation,
)

KINDS = [Recidivism.SIMPLE, Recidivism.DANGEROUS, Recidivism.ESPECIALLY_DANGEROUS]


def _check(**overrides):
    params = {
        "recidivism": Recidivism.SIMPLE,
        "recognized_in_draft": Recidivism.SIMPLE,
        "element_convictions_excluded": False,
    }
    params.update(overrides)
    return check_recidivism_aggravation(**params)


def test_result_is_marked_for_legal_review_with_source():
    result = _check()
    assert NEEDS_LEGAL_REVIEW is True
    assert result.needs_legal_review is True
    assert result.norm == NORM
    assert result.source == SOURCE
    assert "ст. 63" in NORM
    assert "N 58" in SOURCE and "п. 32" in SOURCE


@pytest.mark.parametrize("kind", KINDS)
def test_recognized_with_the_same_kind_is_ok(kind):
    assert _check(recidivism=kind, recognized_in_draft=kind).status is CheckStatus.OK


@pytest.mark.parametrize("kind", KINDS)
def test_recidivism_not_recognized_as_aggravating_is_flagged(kind):
    # The list of ч. 1 ст. 63 is mandatory: an established recidivism must be recognized.
    result = _check(recidivism=kind, recognized_in_draft=Recidivism.NONE)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. «а» ч. 1 ст. 63" in result.explanation


def test_recognized_without_naming_the_kind_is_ok_with_a_hint():
    result = _check(recidivism=Recidivism.DANGEROUS, recognized_in_draft=Recidivism.UNKNOWN)
    assert result.status is CheckStatus.OK
    assert "опасный" in result.explanation


@pytest.mark.parametrize(
    ("computed", "stated"),
    [
        (Recidivism.SIMPLE, Recidivism.DANGEROUS),
        (Recidivism.DANGEROUS, Recidivism.SIMPLE),
        (Recidivism.ESPECIALLY_DANGEROUS, Recidivism.DANGEROUS),
    ],
)
def test_a_different_kind_in_the_draft_is_flagged(computed, stated):
    result = _check(recidivism=computed, recognized_in_draft=stated)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 18" in result.explanation


def test_no_recidivism_and_not_recognized_is_ok():
    result = _check(recidivism=Recidivism.NONE, recognized_in_draft=Recidivism.NONE)
    assert result.status is CheckStatus.OK


@pytest.mark.parametrize("stated", [*KINDS, Recidivism.UNKNOWN])
def test_recognized_although_there_is_no_recidivism_is_flagged(stated):
    result = _check(recidivism=Recidivism.NONE, recognized_in_draft=stated)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 18" in result.explanation


def test_double_counting_of_an_element_conviction_is_explained():
    # ч. 2 ст. 63, Пленум N 58 п. 32: a conviction that is an element of the offence
    # (e.g. ст. 314.1) is not counted again as recidivism.
    result = _check(
        recidivism=Recidivism.NONE,
        recognized_in_draft=Recidivism.SIMPLE,
        element_convictions_excluded=True,
    )
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 2 ст. 63" in result.explanation
    assert "п. 32" in result.explanation


def test_other_convictions_still_form_recidivism_after_excluding_the_element_one():
    result = _check(
        recidivism=Recidivism.SIMPLE,
        recognized_in_draft=Recidivism.SIMPLE,
        element_convictions_excluded=True,
    )
    assert result.status is CheckStatus.OK


def test_unknown_recidivism_gives_insufficient_data():
    result = _check(recidivism=Recidivism.UNKNOWN, recognized_in_draft=Recidivism.SIMPLE)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_draft_position_not_extracted_gives_insufficient_data():
    result = _check(recidivism=Recidivism.SIMPLE, recognized_in_draft=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
