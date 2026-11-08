# Domain test — ч. 2 и 2.1 ст. 58 УК РФ (назначение части срока в тюрьме) с разъяснениями
# Пленума ВС РФ от 29.05.2014 N 9, пп. 5–6.
from dataclasses import replace

import pytest

from legal_core.checks import CheckStatus
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import Sex
from legal_core.rules.art58_prison import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    RULE_KEY,
    SOURCE,
    DraftPrisonPart,
    PrisonPartFacts,
    check_prison_part,
)

OK = CheckStatus.OK
BAD = CheckStatus.POSSIBLE_VIOLATION
UNKNOWN = CheckStatus.INSUFFICIENT_DATA

MAN = PrisonPartFacts(
    conditional=False,
    life_imprisonment=False,
    sex=Sex.MALE,
    minor_at_sentencing=False,
    recidivism=Recidivism.NONE,
    especially_grave_terms_months=(),
    article_in_part2_list=False,
    article_in_part21_list=False,
)
OVER_FIVE = replace(MAN, especially_grave_terms_months=(61,))
LISTED_21 = replace(MAN, article_in_part21_list=True)

NONE = DraftPrisonPart(assigned=False)
MOTIVATED = DraftPrisonPart(assigned=True, months=24, motivated=True)
THREE_YEARS = DraftPrisonPart(assigned=True, months=36, credited_detention_months=6)


def status(facts, draft):
    return check_prison_part(facts, draft).status


def test_result_is_marked_for_legal_review_with_source():
    result = check_prison_part(MAN, NONE)
    assert NEEDS_LEGAL_REVIEW is True and result.needs_legal_review is True
    assert result.norm == NORM and result.source == SOURCE and result.rule_key == RULE_KEY
    assert "ч. 2" in NORM and "2.1" in NORM
    assert "pravo.gov.ru" in SOURCE and "157-ФЗ" in SOURCE and "N 9" in SOURCE


# --- условное осуждение и неизвестные исходные ------------------------------------------------
def test_unknown_conditional_is_insufficient():
    assert status(replace(MAN, conditional=None), NONE) is UNKNOWN


def test_unknown_whether_prison_is_assigned_is_insufficient():
    assert status(OVER_FIVE, DraftPrisonPart(assigned=None)) is UNKNOWN


def test_conditional_without_prison_is_ok():
    assert status(replace(LISTED_21, conditional=True), NONE) is OK


def test_conditional_with_prison_is_flagged():
    assert status(replace(OVER_FIVE, conditional=True), MOTIVATED) is BAD


def test_life_imprisonment_is_not_assessed():
    # Ч. 2 и 2.1 говорят о лишении свободы; пожизненное (ст. 57) здесь не оценивается.
    result = check_prison_part(replace(LISTED_21, life_imprisonment=True), NONE)
    assert result.status is UNKNOWN and "пожизненн" in result.explanation.lower()


# --- ч. 2.1: тюрьма обязательна ----------------------------------------------------------------
def test_listed_21_without_prison_is_flagged():
    result = check_prison_part(LISTED_21, NONE)
    assert result.status is BAD and "2.1" in result.explanation


def test_not_listed_21_without_prison_is_ok_even_if_part2_ground_exists():
    assert status(OVER_FIVE, NONE) is OK


def test_unknown_listing_without_prison_is_insufficient():
    assert status(replace(MAN, article_in_part21_list=None), NONE) is UNKNOWN


@pytest.mark.parametrize(
    "change", [{"sex": None}, {"minor_at_sentencing": None}], ids=["sex", "minor"]
)
def test_listed_21_with_unknown_person_without_prison_is_insufficient(change):
    assert status(replace(LISTED_21, **change), NONE) is UNKNOWN


@pytest.mark.parametrize(
    "change", [{"sex": Sex.FEMALE}, {"minor_at_sentencing": True}], ids=["woman", "minor"]
)
def test_listed_21_does_not_oblige_women_and_minors(change):
    assert status(replace(LISTED_21, **change), NONE) is OK


def test_listed_21_with_enough_term_after_credit_is_ok_without_reasons():
    assert status(LISTED_21, THREE_YEARS) is OK


def test_listed_21_below_one_year_after_credit_is_flagged():
    draft = DraftPrisonPart(assigned=True, months=14, credited_detention_months=3)
    assert status(LISTED_21, draft) is BAD


def test_listed_21_exactly_one_year_after_credit_is_ok():
    draft = DraftPrisonPart(assigned=True, months=15, credited_detention_months=3)
    assert status(LISTED_21, draft) is OK


def test_listed_21_stated_term_below_one_year_is_flagged_without_credit_data():
    assert status(LISTED_21, DraftPrisonPart(assigned=True, months=11)) is BAD


def test_listed_21_enough_stated_term_with_unknown_credit_is_insufficient():
    assert status(LISTED_21, DraftPrisonPart(assigned=True, months=24)) is UNKNOWN


def test_listed_21_unknown_stated_term_is_insufficient():
    assert status(LISTED_21, DraftPrisonPart(assigned=True)) is UNKNOWN


# --- кому тюрьма не назначается --------------------------------------------------------------
def test_prison_for_a_woman_is_flagged():
    assert status(replace(OVER_FIVE, sex=Sex.FEMALE), MOTIVATED) is BAD


def test_prison_for_a_minor_is_flagged():
    assert status(replace(OVER_FIVE, minor_at_sentencing=True), MOTIVATED) is BAD


@pytest.mark.parametrize(
    "change", [{"sex": None}, {"minor_at_sentencing": None}], ids=["sex", "minor"]
)
def test_prison_with_unknown_person_is_insufficient(change):
    assert status(replace(OVER_FIVE, **change), MOTIVATED) is UNKNOWN


def test_prison_with_unknown_21_listing_is_insufficient():
    # Без сведений о ч. 2.1 неясно, нужны ли мотивы и минимальный срок.
    assert status(replace(OVER_FIVE, article_in_part21_list=None), MOTIVATED) is UNKNOWN


# --- ч. 2: основания --------------------------------------------------------------------------
def test_especially_grave_over_five_years_is_a_ground():
    assert status(OVER_FIVE, MOTIVATED) is OK


def test_especially_grave_exactly_five_years_is_no_ground():
    # «на срок свыше пяти лет»: ровно пять лет основанием не является.
    assert status(replace(MAN, especially_grave_terms_months=(60,)), MOTIVATED) is BAD


def test_aggregate_needs_one_especially_grave_term_over_five_years():
    # ППВС № 9 п. 6: срок за само особо тяжкое преступление, а не итог совокупности.
    assert status(replace(MAN, especially_grave_terms_months=(36, 48)), MOTIVATED) is BAD
    assert status(replace(MAN, especially_grave_terms_months=(36, 72)), MOTIVATED) is OK


def test_especially_dangerous_recidivism_is_a_ground_regardless_of_term():
    assert status(replace(MAN, recidivism=Recidivism.ESPECIALLY_DANGEROUS), MOTIVATED) is OK


def test_part2_listed_article_is_a_ground_regardless_of_term():
    assert status(replace(MAN, article_in_part2_list=True), MOTIVATED) is OK


def test_no_ground_is_flagged():
    result = check_prison_part(MAN, MOTIVATED)
    assert result.status is BAD and "основани" in result.explanation


@pytest.mark.parametrize(
    "change",
    [
        {"especially_grave_terms_months": None},
        {"recidivism": Recidivism.UNKNOWN},
        {"article_in_part2_list": None},
    ],
    ids=["terms", "recidivism", "part2-list"],
)
def test_no_ground_with_unknown_fact_is_insufficient(change):
    assert status(replace(MAN, **change), MOTIVATED) is UNKNOWN


def test_known_ground_outweighs_unknown_other_facts():
    facts = replace(OVER_FIVE, recidivism=Recidivism.UNKNOWN, article_in_part2_list=None)
    assert status(facts, MOTIVATED) is OK


# --- ч. 2: срок и мотивы (ППВС № 9 п. 5) --------------------------------------------------------
def test_part2_unstated_term_is_insufficient():
    assert status(OVER_FIVE, DraftPrisonPart(assigned=True, motivated=True)) is UNKNOWN


def test_part2_unknown_reasons_are_insufficient():
    assert status(OVER_FIVE, DraftPrisonPart(assigned=True, months=24)) is UNKNOWN


def test_part2_missing_reasons_are_flagged():
    draft = DraftPrisonPart(assigned=True, months=24, motivated=False)
    result = check_prison_part(OVER_FIVE, draft)
    assert result.status is BAD and "мотив" in result.explanation
