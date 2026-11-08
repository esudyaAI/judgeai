"""T15.2: every check result names its catalog rule, so a finding opens its legal basis."""

import pytest

from legal_core import catalog
from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import (
    Category,
    ImposedPunishment,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
)
from legal_core.rules import (
    art15,
    art18,
    art58,
    art62,
    art63,
    art66,
    art68,
    art73,
    art86,
    imposed_term,
)
from legal_core.rules.art18 import Recidivism

MODULES = [art15, art18, art58, art62, art63, art66, art68, art73, art86, imposed_term]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_rule_module_key_is_a_catalog_rule(module):
    assert catalog.rule(module.RULE_KEY).key == module.RULE_KEY


def test_catalog_lists_exactly_the_rule_modules():
    assert sorted(item.key for item in catalog.RULES) == sorted(m.RULE_KEY for m in MODULES)


def test_result_without_key_stays_compatible():
    result = CheckResult("норма", CheckStatus.OK, "пояснение", "источник")
    assert result.rule_key is None and result.needs_legal_review


def _results() -> dict[str, list[CheckResult]]:
    none = Recidivism.NONE
    months = PunishmentTerm(PunishmentKind.IMPRISONMENT, 12, MeasureUnit.MONTHS)
    return {
        art15.RULE_KEY: [
            art15.check_category_change(
                original=Category.GRAVE,
                claimed=Category.GRAVE,
                has_mitigating=True,
                has_aggravating=False,
                imposed=ImposedPunishment(imprisonment_months=None),
            ),
            art15.check_category_change(
                original=Category.GRAVE,
                claimed=Category.MEDIUM,
                has_mitigating=True,
                has_aggravating=False,
                imposed=ImposedPunishment(imprisonment_months=None),
            ),
        ],
        art58.RULE_KEY: [
            art58.check_correctional_institution(
                [],
                conditional=None,
                draft_institution=None,
                general_instead_of_settlement_motivated=None,
                sex=None,
                minor_at_sentencing=None,
                life_imprisonment=False,
                previously_served=None,
                recidivism=Recidivism.UNKNOWN,
            )
        ],
        art63.RULE_KEY: [
            art63.check_recidivism_aggravation(
                recidivism=none, recognized_in_draft=None, element_convictions_excluded=True
            )
        ],
        art68.RULE_KEY: [
            art68.check_recidivism_term(
                recidivism=none,
                imposed_months=None,
                most_severe_max_months=None,
                imposed_most_severe_kind=True,
                art61_mitigating_established=False,
                art64_applied=False,
            )
        ],
        art66.RULE_KEY: [
            art66.check_unfinished_offence_term(
                stage=art66.OffenceStage.UNKNOWN,
                imposed_months=None,
                most_severe_max_months=None,
                imposed_most_severe_kind=True,
                imposed_life_or_death=False,
            )
        ],
        art73.RULE_KEY: [
            art73.check_conditional_sentence_recidivism_bar(
                recidivism=none, conditional_in_draft=None
            )
        ],
        imposed_term.RULE_KEY: [
            imposed_term.check_imposed_imprisonment(ImposedPunishment(None), [], source="s"),
            imposed_term.check_imposed_imprisonment(ImposedPunishment(12), [], source="s"),
            imposed_term.check_imposed_punishment(months, [], source="s"),
        ],
    }


@pytest.mark.parametrize("key", sorted(_results()))
def test_every_check_result_carries_its_rule_key(key):
    results = _results()[key]
    assert results and all(result.rule_key == key for result in results)
    assert all(catalog.find(result.rule_key) is not None for result in results)
