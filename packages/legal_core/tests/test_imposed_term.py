import pytest

from legal_core.checks import CheckStatus
from legal_core.entities import (
    ImposedPunishment,
    MeasureUnit,
    PunishmentKind,
    SanctionRole,
    StatutorySanction,
)
from legal_core.rules.imposed_term import check_imposed_imprisonment


def _sanction(kind=PunishmentKind.IMPRISONMENT, min_value=None, max_value=60):
    unit = MeasureUnit.MONTHS if max_value else None
    return StatutorySanction("158", 2, kind, SanctionRole.MAIN, min_value, max_value, unit, "...")


def _check(months, sanctions, **kwargs):
    return check_imposed_imprisonment(ImposedPunishment(months), sanctions, source="src", **kwargs)


@pytest.mark.parametrize(
    "months,sanctions,kwargs,status,fragment",
    [
        (36, [_sanction()], {}, CheckStatus.OK, "в пределах"),
        (61, [_sanction()], {}, CheckStatus.POSSIBLE_VIOLATION, "максимуме санкции 60"),
        (
            54,
            [_sanction()],
            {"art62_limit_months": 40},
            CheckStatus.POSSIBLE_VIOLATION,
            "ч. 1 ст. 62",
        ),
        (40, [_sanction()], {"art62_limit_months": 40}, CheckStatus.OK, "в пределах"),
        (24, [_sanction(min_value=36)], {}, CheckStatus.POSSIBLE_VIOLATION, "ниже минимума"),
        (24, [_sanction(min_value=36)], {"art64_applied": True}, CheckStatus.OK, "в пределах"),
        (
            12,
            [_sanction(kind=PunishmentKind.FINE, max_value=None)],
            {},
            CheckStatus.POSSIBLE_VIOLATION,
            "не предусматривает",
        ),
        (None, [_sanction()], {}, CheckStatus.INSUFFICIENT_DATA, "только лишение свободы"),
    ],
)
def test_imposed_imprisonment(months, sanctions, kwargs, status, fragment):
    result = _check(months, sanctions, **kwargs)
    assert result.status is status
    assert fragment in result.explanation
    assert "Не проверены" in result.explanation and result.needs_legal_review


def _any(kind, min_value=None, max_value=None, unit=None):
    return StatutorySanction("158", 1, kind, SanctionRole.MAIN, min_value, max_value, unit, "...")


def test_imposed_punishment_of_other_kinds():
    from legal_core.entities import PunishmentTerm
    from legal_core.rules.imposed_term import check_imposed_punishment

    sanctions = [
        _any(PunishmentKind.FINE, None, 80_000, MeasureUnit.RUBLES),
        _any(PunishmentKind.COMPULSORY_WORKS, None, 360, MeasureUnit.HOURS),
        _any(PunishmentKind.IMPRISONMENT, None, 24, MeasureUnit.MONTHS),
    ]

    def check(kind, amount, unit, **kwargs):
        term = PunishmentTerm(kind, amount, unit)
        return check_imposed_punishment(term, sanctions, source="s", **kwargs)

    assert check(PunishmentKind.FINE, 50_000, MeasureUnit.RUBLES).status is CheckStatus.OK
    over = check(PunishmentKind.COMPULSORY_WORKS, 400, MeasureUnit.HOURS)
    assert over.status is CheckStatus.POSSIBLE_VIOLATION and "360 ч." in over.explanation
    absent = check(PunishmentKind.ARREST, 2, MeasureUnit.MONTHS)
    assert absent.status is CheckStatus.POSSIBLE_VIOLATION
    milder = check(PunishmentKind.ARREST, 2, MeasureUnit.MONTHS, art64_applied=True)
    assert milder.status is CheckStatus.OK
    mismatch = check(PunishmentKind.FINE, 3, MeasureUnit.MONTHS)
    assert mismatch.status is CheckStatus.INSUFFICIENT_DATA
    # ч. 1 ст. 62 limits imprisonment only.
    assert (
        check(PunishmentKind.FINE, 70_000, MeasureUnit.RUBLES, art62_limit_months=16).status
        is CheckStatus.OK
    )


def test_attempt_is_bounded_by_three_quarters_and_named_in_the_norm():
    from legal_core.entities import PunishmentTerm, Unfinished
    from legal_core.rules.imposed_term import check_imposed_punishment

    def check(months, **kwargs):
        term = PunishmentTerm(PunishmentKind.IMPRISONMENT, months, MeasureUnit.MONTHS)
        return check_imposed_punishment(term, [_sanction(max_value=48)], source="s", **kwargs)

    over = check(40, unfinished=Unfinished.ATTEMPT)
    assert over.status is CheckStatus.POSSIBLE_VIOLATION
    assert "36 мес." in over.explanation and "ч. 3 ст. 66" in over.explanation
    assert over.norm == "Назначенное наказание: пределы санкции и ч. 3 ст. 66 УК РФ"
    assert check(18, unfinished=Unfinished.ATTEMPT).status is CheckStatus.OK
    prepared = check(30, unfinished=Unfinished.PREPARATION)
    assert prepared.status is CheckStatus.POSSIBLE_VIOLATION and "24 мес." in prepared.explanation
    assert check(40).status is CheckStatus.OK


def test_norm_names_only_the_limits_that_apply():
    from legal_core.entities import PunishmentTerm, Unfinished
    from legal_core.rules.imposed_term import check_imposed_punishment

    term = PunishmentTerm(PunishmentKind.IMPRISONMENT, 12, MeasureUnit.MONTHS)
    plain = check_imposed_punishment(term, [_sanction()], source="s")
    assert plain.norm == "Назначенное наказание: пределы санкции статьи УК РФ"
    both = check_imposed_punishment(
        term, [_sanction()], source="s", art62_limit_months=30, unfinished=Unfinished.ATTEMPT
    )
    assert both.norm == "Назначенное наказание: пределы санкции, ч. 3 ст. 66 и ч. 1 ст. 62 УК РФ"
