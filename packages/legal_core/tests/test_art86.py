# Domain test — ст. 86 и ст. 95 УК РФ (погашение судимости), ППВС РФ от 07.06.2022 N 14.
from datetime import date

import pytest

from legal_core.entities import Category
from legal_core.rules.art86 import (
    NEEDS_LEGAL_REVIEW,
    SOURCE,
    TERMS_RAISED_ON,
    Disposition,
    SentenceForExpungement,
    add_months,
    expungement,
    record_active_on,
)

FORCE = date(2015, 3, 10)
SERVED = date(2018, 5, 10)


def _sentence(**overrides):
    params = {
        "category": Category.MEDIUM,
        "disposition": Disposition.IMPRISONMENT,
        "offence_date": date(2014, 6, 1),
        "minor_at_offence": False,
        "legal_force_date": FORCE,
        "served_on": SERVED,
    }
    params.update(overrides)
    return SentenceForExpungement(**params)


def test_marked_for_legal_review_with_sources():
    assert NEEDS_LEGAL_REVIEW is True
    assert expungement(_sentence()).needs_legal_review is True
    assert "pravo.gov.ru" in SOURCE and "218-ФЗ" in SOURCE and "N 14" in SOURCE
    assert TERMS_RAISED_ON == date(2013, 8, 3)


def test_add_months_moves_29_february_to_end_of_month():
    assert add_months(date(2016, 2, 29), 12) == date(2017, 2, 28)
    assert add_months(date(2016, 2, 29), 48) == date(2020, 2, 29)
    assert add_months(date(2020, 8, 31), 6) == date(2021, 2, 28)
    assert add_months(date(2020, 1, 15), 0) == date(2020, 1, 15)


@pytest.mark.parametrize(
    ("category", "disposition", "years", "point"),
    [
        (Category.SMALL, Disposition.IMPRISONMENT, 3, "«в»"),
        (Category.MEDIUM, Disposition.IMPRISONMENT, 3, "«в»"),
        (Category.GRAVE, Disposition.IMPRISONMENT, 8, "«г»"),
        (Category.ESPECIALLY_GRAVE, Disposition.IMPRISONMENT, 10, "«д»"),
        (Category.SMALL, Disposition.NON_CUSTODIAL, 1, "«б»"),
        (Category.GRAVE, Disposition.NON_CUSTODIAL, 1, "«б»"),
        # ППВС № 14 п. 5: for an especially grave offence п. «д» applies whatever the punishment.
        (Category.ESPECIALLY_GRAVE, Disposition.NON_CUSTODIAL, 10, "«д»"),
    ],
)
def test_adult_terms_of_part_3(category, disposition, years, point):
    result = expungement(_sentence(category=category, disposition=disposition))
    assert result.last_day == add_months(SERVED, 12 * years)
    assert f"п. {point} ч. 3 ст. 86" in result.basis


@pytest.mark.parametrize(
    ("category", "years", "point"),
    [(Category.GRAVE, 6, "«г»"), (Category.ESPECIALLY_GRAVE, 8, "«д»")],
)
def test_offence_before_218_fz_keeps_the_former_shorter_terms(category, years, point):
    early = _sentence(category=category, offence_date=date(2013, 8, 2))
    result = expungement(early)
    assert result.last_day == add_months(SERVED, 12 * years)
    assert "218-ФЗ" in result.basis and "ст. 10" in result.basis
    assert f"п. {point}" in result.basis


def test_offence_on_the_day_218_fz_took_effect_gets_the_new_term():
    result = expungement(_sentence(category=Category.GRAVE, offence_date=TERMS_RAISED_ON))
    assert result.last_day == add_months(SERVED, 96)


def test_edition_does_not_matter_for_medium_offences_without_offence_date():
    result = expungement(_sentence(category=Category.MEDIUM, offence_date=None))
    assert result.last_day == add_months(SERVED, 36)


def test_unknown_offence_date_blocks_grave_terms():
    result = expungement(_sentence(category=Category.GRAVE, offence_date=None))
    assert result.last_day is None
    assert "дата преступления" in result.basis


@pytest.mark.parametrize(
    ("category", "disposition", "months"),
    [
        (Category.SMALL, Disposition.NON_CUSTODIAL, 6),
        (Category.MEDIUM, Disposition.IMPRISONMENT, 12),
        (Category.GRAVE, Disposition.IMPRISONMENT, 36),
        (Category.ESPECIALLY_GRAVE, Disposition.IMPRISONMENT, 36),
    ],
)
def test_minor_terms_of_article_95(category, disposition, months):
    minor = _sentence(category=category, disposition=disposition, minor_at_offence=True)
    result = expungement(minor)
    assert result.last_day == add_months(SERVED, months)
    assert "ст. 95" in result.basis


def test_minor_with_especially_grave_non_custodial_is_left_to_the_judge():
    minor = _sentence(
        category=Category.ESPECIALLY_GRAVE,
        disposition=Disposition.NON_CUSTODIAL,
        minor_at_offence=True,
    )
    assert expungement(minor).last_day is None


def test_unknown_age_blocks_the_term():
    result = expungement(_sentence(minor_at_offence=None))
    assert result.last_day is None
    assert "несовершеннолет" in result.basis


def test_conditional_sentence_expires_with_probation_counted_from_legal_force():
    conditional = _sentence(
        disposition=Disposition.CONDITIONAL, served_on=None, probation_months=18
    )
    result = expungement(conditional)
    assert result.last_day == add_months(FORCE, 18)
    assert "п. «а» ч. 3 ст. 86" in result.basis


def test_conditional_sentence_is_not_shortened_for_minors():
    conditional = _sentence(
        disposition=Disposition.CONDITIONAL,
        served_on=None,
        probation_months=24,
        minor_at_offence=True,
    )
    assert expungement(conditional).last_day == add_months(FORCE, 24)


@pytest.mark.parametrize(
    "overrides",
    [
        {"probation_months": None},
        {"legal_force_date": None, "probation_months": 12},
    ],
)
def test_conditional_sentence_without_probation_facts_is_unknown(overrides):
    params = {"disposition": Disposition.CONDITIONAL, "served_on": None, **overrides}
    assert expungement(_sentence(**params)).last_day is None


def test_unknown_end_of_serving_blocks_the_term():
    result = expungement(_sentence(served_on=None))
    assert result.last_day is None
    assert "отбыт" in result.basis


def test_early_release_counts_from_release_unless_unserved_part_is_longer():
    # ч. 4 ст. 86: from actual release; ППВС № 14 п. 11: not before the unserved part ends.
    short_rest = _sentence(unserved_until=date(2019, 5, 10))
    assert expungement(short_rest).last_day == add_months(SERVED, 36)
    long_rest = _sentence(unserved_until=date(2023, 1, 1))
    result = expungement(long_rest)
    assert result.last_day == date(2023, 1, 1)
    assert "п. 11" in result.basis


def test_person_released_from_punishment_has_no_record():
    released = _sentence(released_from_punishment=True, served_on=None)
    result = expungement(released)
    assert result.last_day is None
    assert "ч. 2 ст. 86" in result.basis
    assert record_active_on(released, date(2016, 1, 1)) is False


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2015, 3, 9), False),  # before legal force: not yet convicted (ч. 1 ст. 86)
        (FORCE, None),  # same day as legal force: order within the day is unknown
        (date(2016, 1, 1), True),  # while serving
        (date(2021, 5, 9), True),  # inside three years after serving
        (date(2021, 5, 10), None),  # last day: boundary left to the judge
        (date(2021, 5, 11), False),  # expunged
    ],
)
def test_record_active_on_a_day(day, expected):
    assert record_active_on(_sentence(), day) is expected


def test_record_removed_by_court_ends_early():
    removed = _sentence(removed_on=date(2019, 1, 15))
    assert record_active_on(removed, date(2019, 1, 14)) is True
    assert record_active_on(removed, date(2019, 1, 15)) is None
    assert record_active_on(removed, date(2019, 1, 16)) is False


def test_removal_is_decisive_even_when_the_term_is_unknown():
    removed = _sentence(served_on=None, removed_on=date(2019, 1, 15))
    assert record_active_on(removed, date(2020, 1, 1)) is False
    assert record_active_on(removed, date(2018, 1, 1)) is None


def test_unknown_facts_give_unknown_activity():
    assert record_active_on(_sentence(legal_force_date=None), date(2016, 1, 1)) is None
    assert record_active_on(_sentence(served_on=None), date(2016, 1, 1)) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"probation_months": 0, "disposition": Disposition.CONDITIONAL},
        {"probation_months": -3, "disposition": Disposition.CONDITIONAL},
        {"probation_months": 12, "disposition": Disposition.IMPRISONMENT},
        {
            "unserved_until": date(2019, 1, 1),
            "disposition": Disposition.CONDITIONAL,
            "probation_months": 12,
            "served_on": None,
        },
    ],
)
def test_inconsistent_inputs_are_rejected(overrides):
    with pytest.raises(ValueError):
        _sentence(**overrides)
