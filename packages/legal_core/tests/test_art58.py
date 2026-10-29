# Domain test — ч. 1 и ч. 3 ст. 58 УК РФ (вид исправительного учреждения) с разъяснениями
# Пленума ВС РФ от 29.05.2014 N 9 (ред. от 26.11.2024).
import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art58 import (
    NEEDS_LEGAL_REVIEW,
    NORM,
    SOURCE,
    Institution,
    OffenceForRegime,
    Sex,
    check_correctional_institution,
    required_institution,
)

INT = Guilt.INTENTIONAL
NEG = Guilt.NEGLIGENT
S, M, G, EG = Category.SMALL, Category.MEDIUM, Category.GRAVE, Category.ESPECIALLY_GRAVE


def off(category, guilt=INT, *, as_minor=False, imprisonment=True):
    return OffenceForRegime(
        guilt=guilt, category=category, committed_as_minor=as_minor, imprisonment=imprisonment
    )


def need(*offences, **overrides):
    params = {
        "sex": Sex.MALE,
        "minor_at_sentencing": False,
        "life_imprisonment": False,
        "previously_served": False,
        "recidivism": Recidivism.NONE,
    }
    params.update(overrides)
    return required_institution(list(offences), **params)


def check(*offences, draft, motivated=None, conditional=False, **overrides):
    params = {
        "sex": Sex.MALE,
        "minor_at_sentencing": False,
        "life_imprisonment": False,
        "previously_served": False,
        "recidivism": Recidivism.NONE,
    }
    params.update(overrides)
    return check_correctional_institution(
        list(offences),
        conditional=conditional,
        draft_institution=draft,
        general_instead_of_settlement_motivated=motivated,
        **params,
    )


def test_result_is_marked_for_legal_review_with_source():
    result = check(off(G), draft=Institution.GENERAL)
    assert NEEDS_LEGAL_REVIEW is True
    assert result.needs_legal_review is True
    assert result.norm == NORM and result.source == SOURCE
    assert "ст. 58" in NORM
    assert "pravo.gov.ru" in SOURCE and "25-ФЗ" in SOURCE
    assert "N 9" in SOURCE and "26.11.2024" in SOURCE


# --- п. «а» ч. 1: колония-поселение (общий режим — только мотивированно) ---------------------


@pytest.mark.parametrize("category", [S, M, G, EG])
def test_negligent_only_goes_to_settlement_regardless_of_history(category):
    # ППВС № 9 п. 2 «а»: независимо от категории, срока и прежних судимостей.
    assert need(off(category, NEG), previously_served=True) is Institution.SETTLEMENT


@pytest.mark.parametrize("category", [S, M])
def test_intentional_small_or_medium_first_time_goes_to_settlement(category):
    assert need(off(category)) is Institution.SETTLEMENT


def test_grave_without_imprisonment_is_ignored_for_the_regime():
    # ППВС № 9 п. 2 «в»: тяжкое, за которое назначено наказание без лишения свободы.
    assert need(off(M), off(G, imprisonment=False)) is Institution.SETTLEMENT


def test_mixed_negligent_and_intentional_medium_goes_to_settlement():
    assert need(off(EG, NEG), off(M)) is Institution.SETTLEMENT


# --- п. «б» ч. 1 и ППВС № 9 п. 3: общий режим ------------------------------------------------


def test_male_grave_first_time_goes_to_general():
    assert need(off(G), off(S)) is Institution.GENERAL


@pytest.mark.parametrize("category", [S, M, G])
def test_male_previously_served_without_recidivism_goes_to_general(category):
    assert need(off(category), previously_served=True) is Institution.GENERAL


# --- п. «в» ч. 1 и ППВС № 9 п. 4: строгий режим ----------------------------------------------


def test_male_especially_grave_first_time_goes_to_strict():
    assert need(off(EG)) is Institution.STRICT


def test_male_especially_grave_previously_served_without_recidivism_goes_to_strict():
    assert need(off(EG), previously_served=True) is Institution.STRICT


@pytest.mark.parametrize("kind", [Recidivism.SIMPLE, Recidivism.DANGEROUS])
@pytest.mark.parametrize("category", [S, M, G, EG])
def test_male_recidivism_after_served_imprisonment_goes_to_strict(kind, category):
    assert need(off(category), recidivism=kind, previously_served=True) is Institution.STRICT


def test_male_recidivism_without_served_imprisonment_follows_the_category():
    assert need(off(M), recidivism=Recidivism.SIMPLE) is Institution.SETTLEMENT
    assert need(off(G), recidivism=Recidivism.DANGEROUS) is Institution.GENERAL


# --- п. «г» ч. 1: особый режим ---------------------------------------------------------------


def test_male_especially_dangerous_recidivism_goes_to_special():
    result = need(off(M), recidivism=Recidivism.ESPECIALLY_DANGEROUS, previously_served=None)
    assert result is Institution.SPECIAL


def test_male_life_imprisonment_goes_to_special():
    assert need(off(EG), life_imprisonment=True, previously_served=None) is Institution.SPECIAL


# --- женщины: п. «б» ч. 1 и ППВС № 9 п. 8 ----------------------------------------------------


@pytest.mark.parametrize("kind", list(Recidivism))
@pytest.mark.parametrize("category", [G, EG])
def test_female_grave_or_especially_grave_goes_to_general_with_any_recidivism(kind, category):
    result = need(off(category), sex=Sex.FEMALE, recidivism=kind, previously_served=None)
    assert result is Institution.GENERAL


@pytest.mark.parametrize("kind", [Recidivism.NONE, Recidivism.ESPECIALLY_DANGEROUS])
def test_female_small_or_medium_goes_to_settlement_with_any_recidivism(kind):
    result = need(off(M), sex=Sex.FEMALE, recidivism=kind, previously_served=True)
    assert result is Institution.SETTLEMENT


def test_female_life_imprisonment_is_rejected():
    with pytest.raises(ValueError):
        need(off(EG), sex=Sex.FEMALE, life_imprisonment=True)


# --- ч. 3 и ППВС № 9 п. 10: несовершеннолетние -----------------------------------------------


def test_minor_at_sentencing_goes_to_educational_colony():
    result = need(off(EG), sex=None, minor_at_sentencing=True, recidivism=Recidivism.UNKNOWN)
    assert result is Institution.EDUCATIONAL


def test_grave_committed_as_minor_but_adult_at_sentencing_goes_to_general():
    assert need(off(EG, as_minor=True)) is Institution.GENERAL


def test_small_committed_as_minor_follows_settlement_rule():
    assert need(off(M, as_minor=True), previously_served=True) is Institution.SETTLEMENT


def test_minor_and_adult_periods_examples_of_paragraph_10():
    # особо тяжкое до 18 + умышленное средней тяжести после 18 → общий режим;
    assert need(off(EG, as_minor=True), off(M)) is Institution.GENERAL
    # средней тяжести до 18 + особо тяжкое после 18 → строгий режим.
    assert need(off(M, as_minor=True), off(EG)) is Institution.STRICT


# --- неизвестные факты → None ---------------------------------------------------------------


def test_unknown_sex_when_it_matters_gives_none():
    assert need(off(G), sex=None) is None


def test_unknown_minority_gives_none():
    assert need(off(G), minor_at_sentencing=None) is None


def test_unknown_previous_imprisonment_when_it_matters_gives_none():
    assert need(off(G), previously_served=None) is None
    assert need(off(M), recidivism=Recidivism.SIMPLE, previously_served=None) is None


def test_unknown_recidivism_when_it_matters_gives_none():
    assert need(off(M), recidivism=Recidivism.UNKNOWN, previously_served=True) is None
    # особо тяжкое: строгий режим или особый при особо опасном рецидиве — не определить.
    assert need(off(EG), recidivism=Recidivism.UNKNOWN, previously_served=False) is None


def test_unknown_facts_that_do_not_matter_are_ignored():
    assert need(off(M, NEG), sex=None, previously_served=None) is Institution.SETTLEMENT
    assert need(off(EG, NEG), recidivism=Recidivism.UNKNOWN) is Institution.SETTLEMENT


def test_no_offence_with_imprisonment_is_rejected():
    with pytest.raises(ValueError):
        need(off(G, imprisonment=False))
    with pytest.raises(ValueError):
        need()


# --- проверка проекта -----------------------------------------------------------------------


def test_matching_institution_is_ok():
    result = check(off(EG), draft=Institution.STRICT)
    assert result.status is CheckStatus.OK
    assert "строгого режима" in result.explanation
    assert "тюрьм" in result.explanation  # ч. 2 и 2.1 не проверялись


def test_different_institution_is_flagged_with_both_names():
    result = check(off(G), draft=Institution.STRICT)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "общего режима" in result.explanation and "строгого режима" in result.explanation


def test_general_instead_of_settlement_with_motives_is_ok():
    result = check(off(M), draft=Institution.GENERAL, motivated=True)
    assert result.status is CheckStatus.OK
    assert "мотив" in result.explanation


def test_general_instead_of_settlement_without_motives_is_flagged():
    result = check(off(M), draft=Institution.GENERAL, motivated=False)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "мотив" in result.explanation


def test_general_instead_of_settlement_with_unknown_motives_is_insufficient():
    result = check(off(M), draft=Institution.GENERAL, motivated=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_stricter_than_general_in_settlement_case_is_flagged():
    result = check(off(M), draft=Institution.STRICT, motivated=True)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION


def test_missing_draft_institution_is_insufficient():
    result = check(off(G), draft=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_undetermined_requirement_is_insufficient():
    result = check(off(G), draft=Institution.GENERAL, sex=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA


def test_conditional_sentence_must_not_name_an_institution():
    # ППВС № 9 п. 18: при условном осуждении вид учреждения не назначается.
    assert check(off(G), draft=None, conditional=True).status is CheckStatus.OK
    flagged = check(off(G), draft=Institution.GENERAL, conditional=True)
    assert flagged.status is CheckStatus.POSSIBLE_VIOLATION
    assert "п. 18" in flagged.explanation


def test_conditional_sentence_skips_unknown_facts():
    result = check(off(G), draft=None, conditional=True, sex=None, previously_served=None)
    assert result.status is CheckStatus.OK


def test_unknown_conditionality_is_insufficient():
    result = check(off(G), draft=Institution.GENERAL, conditional=None)
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "ст. 73" in result.explanation
