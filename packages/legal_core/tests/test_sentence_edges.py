import pytest

from legal_core.checks import CheckStatus as S
from legal_core.entities import (
    Category as C,
)
from legal_core.entities import (
    MeasureUnit as U,
)
from legal_core.entities import (
    PunishmentKind as K,
)
from legal_core.entities import (
    PunishmentTerm as T,
)
from legal_core.entities import (
    SanctionRole as R,
)
from legal_core.entities import (
    StatutorySanction as A,
)
from legal_core.entities import (
    Unfinished as F,
)
from legal_core.rules.art18 import Recidivism
from legal_core.rules.art68 import check_recidivism_amount
from legal_core.rules.imposed_term import check_imposed_punishment
from legal_core.rules.sentence_edges import (
    check_additional,
    check_article69_part,
    check_article70,
    imprisonment_equivalent,
)


def prison(n):
    return T(K.IMPRISONMENT, n, U.MONTHS)


@pytest.mark.parametrize(
    "final,new,balance,joined,status",
    [
        (27, 24, 12, 3, S.OK),
        (24, 24, 12, 3, S.POSSIBLE_VIOLATION),
        (27, 24, 30, 3, S.POSSIBLE_VIOLATION),
        (40, 24, 12, 16, S.POSSIBLE_VIOLATION),
        (27, 24, None, 3, S.INSUFFICIENT_DATA),
        (27, 24, 12, 4, S.POSSIBLE_VIOLATION),
        (361, 300, 100, 61, S.POSSIBLE_VIOLATION),
    ],
)
def test_both_art70_lower_bounds_and_joined_arithmetic(final, new, balance, joined, status):
    assert (
        check_article70(
            prison(final), prison(new), prison(balance) if balance else None, prison(joined)
        ).status
        is status
    )


def test_art71_conversion_and_independently_executed_fine():
    assert imprisonment_equivalent(T(K.COMPULSORY_WORKS, 240, U.HOURS)) == 1
    assert imprisonment_equivalent(T(K.CORRECTIONAL_WORKS, 9, U.MONTHS)) == 3
    assert imprisonment_equivalent(T(K.RESTRICTION_OF_FREEDOM, 6, U.MONTHS)) == 3
    assert imprisonment_equivalent(T(K.IMPRISONMENT, 90, U.DAYS)) == 3
    assert (
        check_article70(
            prison(27),
            prison(24),
            T(K.CORRECTIONAL_WORKS, 12, U.MONTHS),
            T(K.IMPRISONMENT, 90, U.DAYS),
        ).status
        is S.OK
    )
    assert imprisonment_equivalent(T(K.FINE, 1000, U.RUBLES)) is None
    assert (
        check_article70(prison(27), prison(24), T(K.FINE, 1000, U.RUBLES), None).status
        is S.INSUFFICIENT_DATA
    )


@pytest.mark.parametrize(
    "part,categories,stages,status",
    [
        (2, [C.MEDIUM, C.GRAVE], [None, None], S.POSSIBLE_VIOLATION),
        (2, [C.MEDIUM, C.ESPECIALLY_GRAVE], [None, F.ATTEMPT], S.OK),
        (3, [C.MEDIUM, C.GRAVE], [None, None], S.OK),
        (3, [C.MEDIUM, C.GRAVE], [None, F.PREPARATION], S.POSSIBLE_VIOLATION),
        (2, [C.MEDIUM, None], [None, None], S.INSUFFICIENT_DATA),
        (5, [C.GRAVE], [None], S.INSUFFICIENT_DATA),
    ],
)
def test_art69_correct_part_including_unfinished_especially_grave(part, categories, stages, status):
    assert check_article69_part(part, categories, stages).status is status


def test_absorption_for_art69_part3_is_not_valid_addition():
    assert (
        check_article69_part(3, [C.GRAVE], [None], absorption=True).status is S.POSSIBLE_VIOLATION
    )


def test_additional_role_and_statutory_bound():
    sanctions = [
        A("111", 2, K.RESTRICTION_OF_FREEDOM, R.ADDITIONAL, None, 24, U.MONTHS, "до двух лет")
    ]
    assert check_additional(T(K.RESTRICTION_OF_FREEDOM, 24, U.MONTHS), sanctions).status is S.OK
    assert (
        check_additional(T(K.RESTRICTION_OF_FREEDOM, 25, U.MONTHS), sanctions).status
        is S.POSSIBLE_VIOLATION
    )
    assert check_additional(T(K.FINE, 1000, U.RUBLES), sanctions).status is S.POSSIBLE_VIOLATION
    assert (
        check_additional(T(K.DEPRIVATION_OF_RIGHT, 12, U.MONTHS), sanctions).status
        is S.INSUFFICIENT_DATA
    )


@pytest.mark.parametrize(
    "kind,unit,maximum,imposed,stage,status",
    [
        (K.COMPULSORY_WORKS, U.HOURS, 300, 226, F.ATTEMPT, S.POSSIBLE_VIOLATION),
        (K.FINE, U.RUBLES, 100000, 50000, F.PREPARATION, S.OK),
        (K.CORRECTIONAL_WORKS, U.MONTHS, 18, 13.5, F.ATTEMPT, S.OK),
        (K.FORCED_LABOUR, U.MONTHS, 36, 28, F.ATTEMPT, S.POSSIBLE_VIOLATION),
    ],
)
def test_unfinished_limit_for_most_severe_non_custodial_punishment(
    kind, unit, maximum, imposed, stage, status
):
    sanctions = [A("999", 1, kind, R.MAIN, None, maximum, unit, "синтетика")]
    assert (
        check_imposed_punishment(
            T(kind, imposed, unit), sanctions, source="", unfinished=stage
        ).status
        is status
    )


def test_exact_third_does_not_round_to_whole_month():
    kwargs = dict(
        recidivism=Recidivism.SIMPLE,
        maximum=52,
        most_severe_kind=True,
        mitigating=False,
        art64=False,
        unit_name="мес.",
    )
    assert check_recidivism_amount(amount=17, **kwargs).status is S.POSSIBLE_VIOLATION
    assert check_recidivism_amount(amount=17.5, **kwargs).status is S.OK


def test_additional_aggregate_and_other_punishment_totals():
    from legal_core.rules.sentence_edges import check_additional_aggregate, check_other_aggregate

    def restriction(n):
        return T(K.RESTRICTION_OF_FREEDOM, n, U.MONTHS)

    assert (
        check_additional_aggregate(restriction(24), [restriction(12), restriction(18)]).status
        is S.OK
    )
    assert (
        check_additional_aggregate(restriction(25), [restriction(12), restriction(18)]).status
        is S.POSSIBLE_VIOLATION
    )

    def works(n):
        return T(K.COMPULSORY_WORKS, n, U.HOURS)

    assert (
        check_other_aggregate(works(360), [works(200), works(200)], [300, 300], "69.2").status
        is S.OK
    )
    assert (
        check_other_aggregate(works(500), [works(300), works(300)], [480, 480], "69.2").status
        is S.POSSIBLE_VIOLATION
    )
    assert (
        check_other_aggregate(prison(12), [works(200)], [300], "69.2").status is S.INSUFFICIENT_DATA
    )


def test_day_exactly_on_recidivism_boundary_and_fractional_art62():
    from fractions import Fraction

    from legal_core.rules.art62 import part1_limit_amount

    assert (
        check_recidivism_amount(
            recidivism=Recidivism.SIMPLE,
            amount=Fraction(520, 30),
            maximum=52,
            most_severe_kind=True,
            mitigating=False,
            art64=False,
            unit_name="мес.",
        ).status
        is S.OK
    )
    assert part1_limit_amount(5.25, ["п. «и» ч. 1 ст. 61"], has_aggravating=False) == Fraction(7, 2)
    sanction = A("999", 1, K.IMPRISONMENT, R.MAIN, None, 7, U.MONTHS, "до 7 месяцев")
    assert (
        check_imposed_punishment(
            T(K.IMPRISONMENT, 106, U.DAYS),
            [sanction],
            source="",
            unfinished=F.ATTEMPT,
            art62_limit_amount=Fraction(7, 2),
        ).status
        is S.POSSIBLE_VIOLATION
    )


@pytest.mark.parametrize(
    "offence,prior,credited,status",
    [
        ("2020-01-01", "2020-02-02", True, S.OK),
        ("2020-03-01", "2020-02-02", True, S.POSSIBLE_VIOLATION),
        ("2020-02-02", "2020-02-02", True, S.INSUFFICIENT_DATA),
        ("2020-01-01", "2020-02-02", False, S.INSUFFICIENT_DATA),
        (None, "2020-02-02", True, S.INSUFFICIENT_DATA),
    ],
)
def test_art69_part5_chronology_and_credit(offence, prior, credited, status):
    from datetime import date

    from legal_core.rules.sentence_edges import check_prior_chronology

    assert (
        check_prior_chronology(
            [date.fromisoformat(offence) if offence else None],
            date.fromisoformat(prior),
            prison(6) if credited else None,
        ).status
        is status
    )


def test_article70_unchanged_main_with_additional_annexation_is_not_a_violation():
    """Only the unserved additional punishment is annexed: the main term stays equal."""

    def right_of(n):
        return T(K.DEPRIVATION_OF_RIGHT, n, U.MONTHS)

    main = prison(12)
    unchanged = check_article70(main, main, right_of(13.6), None, additional_only=True)
    assert unchanged.status is S.OK
    assert "дополнительного наказания" in unchanged.explanation
    # Without the additional-annexation context the strict ч. 4 ст. 70 rule still flags.
    assert check_article70(main, main, None, None).status is S.POSSIBLE_VIOLATION
    # A wrong main term is flagged even when an additional punishment was annexed.
    assert (
        check_article70(prison(9), prison(12), right_of(13.6), None, additional_only=True).status
        is S.POSSIBLE_VIOLATION
    )
    # The increased main term under a real aggregate (12 + 11) stays OK.
    assert (
        check_article70(prison(23), prison(12), prison(11), prison(11), additional_only=True).status
        is S.OK
    )


def test_additional_aggregate_includes_the_prior_unserved_part():
    """ст. 70 may partially annex the prior unserved additional punishment."""
    from legal_core.rules.sentence_edges import check_additional_aggregate

    def right_of(n):
        return T(K.DEPRIVATION_OF_RIGHT, n, U.MONTHS)

    # 24 months for the new offence + 13.6 unserved annexed partially = 30 final.
    assert (
        check_additional_aggregate(
            right_of(30), [right_of(24)], 36, prior_parts=(right_of(13.6), None)
        ).status
        is S.OK
    )
    # Without the prior part the same final exceeds the sum of this verdict's counts.
    assert (
        check_additional_aggregate(right_of(30), [right_of(24)], 36).status is S.POSSIBLE_VIOLATION
    )
    # The overall cap still applies with the prior part.
    assert (
        check_additional_aggregate(
            right_of(40), [right_of(24)], 36, prior_parts=(right_of(13.6), None)
        ).status
        is S.POSSIBLE_VIOLATION
    )


def test_additional_aggregate_unread_prior_part_is_insufficient_not_a_violation():
    """Annexed but unread unserved additional punishment: no violation is claimed."""
    from legal_core.rules.sentence_edges import check_additional_aggregate

    def right_of(n):
        return T(K.DEPRIVATION_OF_RIGHT, n, U.MONTHS)

    result = check_additional_aggregate(right_of(30), [right_of(24)], 36, prior_missing=True)
    assert result.status is S.INSUFFICIENT_DATA
    assert "не прочитан" in result.explanation
    # Without the annexation context the excess over this verdict's counts is still a flag.
    assert (
        check_additional_aggregate(right_of(30), [right_of(24)], 36).status is S.POSSIBLE_VIOLATION
    )
