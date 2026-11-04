import unittest

from legal_core.entities import CountSentence, ImposedSentence, PunishmentKind

from src.domain.prepared_legal import PreparedFact
from src.domain.prepared_sentencing import PreparedSentencingInputs
from src.domain.sentence_review import (
    read_date,
    read_term,
    set_sentence_fact,
    validate_sentence_value,
)


class SentenceReviewTest(unittest.TestCase):
    def test_known_kind_with_unknown_amount_is_distinct_from_unknown_whole_term(self):
        term = read_term({"kind": "imprisonment", "amount": None, "unit": None})
        self.assertEqual(term.kind, PunishmentKind.IMPRISONMENT)
        self.assertIsNone(term.imprisonment_months)
        prepared = PreparedSentencingInputs(
            ImposedSentence(counts=(CountSentence("synthetic", None, term),)),
            art64_by_count=(PreparedFact(),),
            guilt_by_count=(PreparedFact(),),
        )
        changed = set_sentence_fact(prepared, ["sentence", "count", "0", "main"], None, "")
        self.assertIn("count/0/main", changed.unknown_fields)
        self.assertEqual(changed.sentence.counts[0].main, term)

    def test_new_sentence_has_unknown_conditional_and_stage_until_asserted(self):
        prepared = PreparedSentencingInputs(None, guilt_by_count=())
        added = set_sentence_fact(
            prepared,
            ["sentence", "count", "new"],
            {
                "qualification": "ч. 2 ст. 158 УК РФ",
                "main": {"kind": "imprisonment", "amount": 24, "unit": "months"},
            },
            "Синтетическая цитата",
        )
        self.assertIn("conditional", added.unknown_fields)
        self.assertTrue(added.sentence.counts[0].stage_conflict)
        self.assertIsNone(added.guilt_by_count[0].value)
        self.assertIsNone(added.art64_by_count[0].value)
        known = set_sentence_fact(added, ["sentence", "conditional"], False, "Не условно")
        self.assertNotIn("conditional", known.unknown_fields)
        self.assertIs(known.sentence.conditional, False)

    def test_dates_are_exact_and_term_units_follow_kind(self):
        self.assertEqual(read_date("2024-02-29").day, 29)
        for value in ("2023-02-29", "20240229", "2024-02-29T00:00:00", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_date(value)
        for value in (
            {"kind": "fine", "amount": 100, "unit": "months"},
            {"kind": "imprisonment", "amount": True, "unit": "months"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_term(value)

    def test_prior_false_is_valid_and_mistyped_flag_is_rejected(self):
        self.assertTrue(
            validate_sentence_value(
                "prior", {"judgment_id": "J1", "conditional_or_deferred": False}
            )
        )
        with self.assertRaises(ValueError):
            validate_sentence_value("prior", {"judgment_id": "J1", "conditional_or_deferred": 0})

    def test_empty_parsed_sentence_does_not_supply_conditional_false_to_new_count(self):
        prepared = PreparedSentencingInputs(
            ImposedSentence(), guilt_by_count=(), aggregate_absorption=(False, False)
        )
        changed = set_sentence_fact(
            prepared,
            ["sentence", "count", "new"],
            {
                "qualification": "ч. 2 ст. 158 УК РФ",
                "main": {"kind": "imprisonment", "amount": 24, "unit": "months"},
            },
            "Синтетическая цитата",
        )
        self.assertIn("conditional", changed.unknown_fields)
        self.assertEqual(changed.aggregate_absorption, (None, None))
