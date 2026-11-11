# Domain test — ч. 2 и ч. 3 ст. 69 УК РФ (совокупность преступлений).
import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import Category
from legal_core.rules.art66 import OffenceStage
from legal_core.rules.art69 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    RULE_KEY,
    SOURCE,
    CumulatedOffence,
    CumulationMethod,
    DraftOffencesCumulation,
    OffencesCumulationFacts,
    check_offences_cumulation,
    cumulation_part,
    exceeds_cumulation_limit,
)

DONE = OffenceStage.COMPLETED
MEDIUM = CumulatedOffence(Category.MEDIUM, DONE)
SMALL = CumulatedOffence(Category.SMALL, DONE)
GRAVE = CumulatedOffence(Category.GRAVE, DONE)
GRAVE_ATTEMPT = CumulatedOffence(Category.GRAVE, OffenceStage.ATTEMPT)
PART2 = (SMALL, MEDIUM)
PART3 = (MEDIUM, GRAVE)


def _facts(offences=PART2, maximum=60):
    return OffencesCumulationFacts(offences=offences, most_serious_max_months=maximum)


def _draft(months, method=CumulationMethod.PARTIAL_ADDITION, *, imprisonment=True, cumul=True):
    return DraftOffencesCumulation(
        by_cumulation=cumul, method=method, final_months=months, imprisonment=imprisonment
    )


def test_result_names_rule_norm_and_source():
    result = check_offences_cumulation(_facts(), _draft(70))
    assert result.rule_key == RULE_KEY == "art69.offences_cumulation"
    assert result.norm == NORM
    assert result.source == SOURCE and "pravo.gov.ru" in SOURCE
    assert result.needs_legal_review is NEEDS_LEGAL_REVIEW is True


# --- which part applies -------------------------------------------------------------------


def test_part2_when_all_offences_small_or_medium():
    assert cumulation_part(PART2) == 2


def test_part2_when_grave_offence_is_only_prepared_or_attempted():
    prepared = CumulatedOffence(Category.ESPECIALLY_GRAVE, OffenceStage.PREPARATION)
    assert cumulation_part((MEDIUM, GRAVE_ATTEMPT, prepared)) == 2


def test_part3_when_at_least_one_completed_grave_offence():
    assert cumulation_part(PART3) == 3
    especially = CumulatedOffence(Category.ESPECIALLY_GRAVE, DONE)
    assert cumulation_part((GRAVE_ATTEMPT, especially)) == 3


def test_completed_grave_decides_part3_despite_unknown_other_offences():
    unknown = CumulatedOffence(None, OffenceStage.UNKNOWN)
    assert cumulation_part((unknown, GRAVE)) == 3


@pytest.mark.parametrize(
    "offence",
    [
        CumulatedOffence(None, DONE),
        CumulatedOffence(Category.GRAVE, OffenceStage.UNKNOWN),
    ],
)
def test_part_unknown_when_a_fact_could_make_it_part3(offence):
    assert cumulation_part((MEDIUM, offence)) is None


def test_unknown_stage_of_small_offence_does_not_matter():
    assert cumulation_part((MEDIUM, CumulatedOffence(Category.SMALL, OffenceStage.UNKNOWN))) == 2


def test_part_unknown_without_offences():
    assert cumulation_part(()) is None


# --- limit: not more than half over the maximum --------------------------------------------


def test_limit_is_one_and_a_half_maximum_without_rounding():
    assert exceeds_cumulation_limit(90, 60) is False
    assert exceeds_cumulation_limit(91, 60) is True
    # 5 months maximum → limit 7.5 months: 7 is within, 8 is over.
    assert exceeds_cumulation_limit(7, 5) is False
    assert exceeds_cumulation_limit(8, 5) is True


def test_limit_rejects_non_positive_maximum():
    with pytest.raises(ValueError):
        exceeds_cumulation_limit(10, 0)


# --- check ----------------------------------------------------------------------------------


def test_not_by_cumulation_is_ok():
    result = check_offences_cumulation(_facts(), _draft(None, None, cumul=False))
    assert result.status is CheckStatus.OK


def test_unknown_whether_by_cumulation_is_insufficient():
    result = check_offences_cumulation(_facts(), _draft(70, cumul=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize("months", [60, 90])
@pytest.mark.parametrize("offences", [PART2, PART3])
def test_within_limit_is_ok(offences, months):
    result = check_offences_cumulation(_facts(offences), _draft(months))
    assert result.status is CheckStatus.OK


@pytest.mark.parametrize("offences,part", [(PART2, "ч. 2 ст. 69"), (PART3, "ч. 3 ст. 69")])
def test_over_limit_is_possible_violation(offences, part):
    result = check_offences_cumulation(_facts(offences), _draft(91))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "91 мес." in result.explanation and "90 мес." in result.explanation
    assert part in result.explanation


def test_absorption_allowed_under_part2():
    result = check_offences_cumulation(_facts(), _draft(60, CumulationMethod.ABSORPTION))
    assert result.status is CheckStatus.OK


def test_absorption_under_part3_is_possible_violation():
    result = check_offences_cumulation(_facts(PART3), _draft(60, CumulationMethod.ABSORPTION))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "поглощ" in result.explanation and "ч. 3 ст. 69" in result.explanation


def test_both_violations_are_listed_together():
    result = check_offences_cumulation(_facts(PART3), _draft(100, CumulationMethod.ABSORPTION))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "поглощ" in result.explanation and "100 мес." in result.explanation


def test_imprisonment_over_limit_is_violation_even_if_part_unknown():
    offences = (MEDIUM, CumulatedOffence(None, DONE))
    result = check_offences_cumulation(_facts(offences), _draft(91, None))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ст. 69" in result.explanation


def test_part_unknown_and_method_unknown_is_insufficient():
    offences = (MEDIUM, CumulatedOffence(None, DONE))
    result = check_offences_cumulation(_facts(offences), _draft(80, None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "тяжк" in result.explanation


def test_part3_unknown_method_is_insufficient():
    result = check_offences_cumulation(_facts(PART3), _draft(80, None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "способ" in result.explanation


def test_part2_unknown_method_is_still_ok():
    result = check_offences_cumulation(_facts(), _draft(80, None))
    assert result.status is CheckStatus.OK


def test_part2_limit_applies_to_any_kind_of_punishment():
    result = check_offences_cumulation(_facts(), _draft(91, imprisonment=False))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_part3_limit_for_other_kind_is_not_modelled():
    result = check_offences_cumulation(_facts(PART3), _draft(91, imprisonment=False))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "лишени" in result.explanation


def test_part3_unknown_kind_is_insufficient():
    result = check_offences_cumulation(_facts(PART3), _draft(80, imprisonment=None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_unknown_maximum_is_insufficient():
    result = check_offences_cumulation(_facts(maximum=None), _draft(80))
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "максимальн" in result.explanation


def test_unknown_final_term_is_insufficient():
    result = check_offences_cumulation(_facts(), _draft(None))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_absorption_violation_reported_even_if_final_term_unknown():
    result = check_offences_cumulation(_facts(PART3), _draft(None, CumulationMethod.ABSORPTION))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_life_imprisonment_is_insufficient():
    draft = DraftOffencesCumulation(True, CumulationMethod.PARTIAL_ADDITION, None, True, True)
    result = check_offences_cumulation(_facts(PART3), draft)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_no_offences_is_insufficient():
    result = check_offences_cumulation(_facts(()), _draft(80, None, imprisonment=False))
    assert result.status is CheckStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize("months,maximum", [(-1, 60), (10, -5), (10, 0)])
def test_invalid_terms_are_rejected(months, maximum):
    with pytest.raises(ValueError):
        check_offences_cumulation(_facts(maximum=maximum), _draft(months))


def test_imprisonment_within_limit_is_ok_even_if_part_unknown():
    offences = (MEDIUM, CumulatedOffence(None, DONE))
    result = check_offences_cumulation(_facts(offences), _draft(90))
    assert result.status is CheckStatus.OK
    assert "ч. None" not in result.explanation and "ст. 69" in result.explanation
