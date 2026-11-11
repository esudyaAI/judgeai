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
    art58_prison,
    art62,
    art63,
    art66,
    art68,
    art69,
    art70,
    art73,
    art86,
    imposed_term,
)
from legal_core.rules.art18 import Recidivism

_MEDIUM_DONE = art69.CumulatedOffence(Category.MEDIUM, art66.OffenceStage.COMPLETED)

MODULES = [
    art15,
    art18,
    art58,
    art58_prison,
    art62,
    art63,
    art66,
    art68,
    art69,
    art70,
    art73,
    art86,
    imposed_term,
]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_rule_module_key_is_a_catalog_rule(module):
    assert catalog.rule(module.RULE_KEY).key == module.RULE_KEY


def test_catalog_lists_exactly_the_rule_modules():
    expected = [m.RULE_KEY for m in MODULES] + [
        art62.RULE_KEY_PART5,
        art62.AGREEMENT_RULE_KEY,
        art73.SUPERVISION_RULE_KEY,
        art73.LIMITS_RULE_KEY,
        art73.OFFENCE_LIST_RULE_KEY,
        art58_prison.NEW_OFFENCE_RULE_KEY,
        art63.INTOXICATION_RULE_KEY,
    ]
    assert sorted(item.key for item in catalog.RULES) == sorted(expected)


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
        art62.RULE_KEY_PART5: [
            art62.check_procedure_term(
                procedure=art62.ProcedureKind.UNKNOWN,
                imposed_months=None,
                most_severe_max_months=None,
                imposed_most_severe_kind=True,
            )
        ],
        art62.AGREEMENT_RULE_KEY: [
            art62.check_pretrial_agreement_term(
                art62.PretrialAgreementFacts(*facts),
                art62.DraftAgreementTerm(False, True, months, 120),
            )
            for facts, months in (
                ((True, True, False, False), 60),
                ((True, True, False, False), 61),
                ((None, None, None, None), None),
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
        art73.LIMITS_RULE_KEY: [
            art73.check_conditional_sentence_limits(
                final_kind=kind, final_months=months, conditional_in_draft=conditional
            )
            for kind, months, conditional in (
                (PunishmentKind.IMPRISONMENT, 120, True),
                (PunishmentKind.FINE, None, True),
                (None, None, None),
            )
        ],
        art73.OFFENCE_LIST_RULE_KEY: [
            art73.check_conditional_sentence_offence_bar(
                offences=offences, conditional_in_draft=conditional
            )
            for offences, conditional in (
                ([art73.ListedOffence("ст. 134", True, None)], True),
                ([art73.ListedOffence("ст. 158", False, False)], True),
                (None, None),
            )
        ],
        art63.INTOXICATION_RULE_KEY: [
            art63.check_intoxication_aggravation(art63.IntoxicationFacts(*values))
            for values in (
                (True, True, False, True),
                (True, True, True, True),
                (None, None, None, None),
            )
        ],
        art58_prison.NEW_OFFENCE_RULE_KEY: [
            art58_prison.check_new_offence_in_prison(
                art58_prison.PrisonNewOffenceFacts(True, 12, False),
                art58_prison.DraftCumulativePrison(True, months, True),
            )
            for months in (6, 12)
        ]
        + [
            art58_prison.check_new_offence_in_prison(
                art58_prison.PrisonNewOffenceFacts(None, None, False),
                art58_prison.DraftCumulativePrison(None, None, None),
            )
        ],
        art69.RULE_KEY: [
            art69.check_offences_cumulation(
                art69.OffencesCumulationFacts(offences, 60),
                art69.DraftOffencesCumulation(cumulation, method, months, True),
            )
            for offences, cumulation, method, months in (
                ((_MEDIUM_DONE,), True, art69.CumulationMethod.FULL_ADDITION, 80),
                ((_MEDIUM_DONE,), True, art69.CumulationMethod.FULL_ADDITION, 100),
                ((), None, None, None),
            )
        ],
        art70.RULE_KEY: [
            art70.check_cumulative_sentences(
                art70.SentencesCumulationFacts(36, 24, part5),
                art70.DraftCumulativeSentence(cumulation, months),
            )
            for part5, cumulation, months in (
                (False, True, 48),
                (False, True, 30),
                (None, None, None),
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
