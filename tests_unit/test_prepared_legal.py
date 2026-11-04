"""Independent prepared-fact evaluation: no DB, HTTP, framework or model fixtures."""

import unittest
from dataclasses import replace

from legal_core.precedents import Recidivism

from src.domain.prepared_legal import PreparedFact, PreparedLegalInputs, evaluate_legal_inputs


def fact(value):
    return PreparedFact(value, "Синтетическая цитата источника")


def current():
    return PreparedLegalInputs(
        model_guilt=fact("intentional"),
        category=fact("grave"),
        real_imprisonment=fact(True),
        history_complete=fact(True),
    )


def prior(**changes):
    values = dict(
        judgment_id="synthetic-judgment",
        guilt="intentional",
        category="grave",
        adult_at_offence=True,
        active_at_offence=True,
        convicted_before_offence=True,
        imprisoned_by_sentence=True,
        conditional_or_deferred=False,
        revoked_and_sent_before_offence=False,
    )
    values.update(changes)
    return tuple((name, fact(value)) for name, value in values.items())


class PreparedLegalTests(unittest.TestCase):
    def test_prior_flags_false_and_unknown_have_different_meanings(self):
        active = replace(current(), prior_convictions=(prior(),))
        inactive = replace(current(), prior_convictions=(prior(active_at_offence=False),))
        missing = replace(current(), prior_convictions=(prior(active_at_offence=None),))
        self.assertEqual(evaluate_legal_inputs(active).recidivism, "dangerous")
        self.assertEqual(evaluate_legal_inputs(inactive).recidivism, "none")
        self.assertIsNone(evaluate_legal_inputs(missing).recidivism)

    def test_duplicate_judgments_do_not_count_as_distinct_priors(self):
        inputs = replace(current(), prior_convictions=(prior(), prior()))
        self.assertIsNone(evaluate_legal_inputs(inputs).recidivism)

    def test_conflicting_court_statement_is_not_an_input_to_later_rules(self):
        inputs = replace(
            current(),
            prior_convictions=(prior(),),
            stated_recidivism=Recidivism.NONE,
            stated_quote="Синтетическое указание суда",
        )
        result = evaluate_legal_inputs(inputs)
        self.assertEqual(result.recidivism, "dangerous")
        self.assertTrue(result.recidivism_conflict)
        self.assertIsNone(result.recidivism_input)

    def test_unknown_history_never_becomes_explicitly_complete(self):
        inputs = replace(current(), history_complete=PreparedFact())
        self.assertIsNone(evaluate_legal_inputs(inputs).recidivism)
