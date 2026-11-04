import unittest
from dataclasses import replace

from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism

from src.domain.prepared_legal import PreparedFact
from src.domain.prepared_sentencing import (
    PreparedCircumstance,
    PreparedRegimeInputs,
    PreparedSentencingInputs,
    evaluate_regime_inputs,
)


class PreparedSentencingTests(unittest.TestCase):
    def regime(self):
        return PreparedRegimeInputs(
            PreparedFact("general", "Назначен общий режим"),
            PreparedFact(False, "Осуждённая"),
            PreparedFact(False, "Ранее не отбывала"),
            True,
        )

    def test_false_is_known_and_unknown_stays_unknown(self):
        known = self.regime()
        unknown = replace(known, male=PreparedFact())
        args = (Recidivism.NONE, Category.GRAVE, Guilt.INTENTIONAL)
        self.assertEqual(evaluate_regime_inputs(known, *args).status.value, "ok")
        self.assertEqual(evaluate_regime_inputs(unknown, *args).status.value, "insufficient_data")

    def test_invalid_regime_or_non_boolean_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.regime(), imposed=PreparedFact("invented", "Синтетическая цитата"))
        with self.assertRaises(ValueError):
            replace(self.regime(), male=PreparedFact("false", "Синтетическая цитата"))

    def test_exceptions_must_match_counts(self):
        with self.assertRaises(ValueError):
            PreparedSentencingInputs(sentence=None, art64_by_count=(PreparedFact(),))

    def test_known_circumstances_require_quoted_support(self):
        with self.assertRaises(ValueError):
            PreparedCircumstance("Синтетическое обстоятельство", "ст. 61", "")
