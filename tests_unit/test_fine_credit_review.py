import unittest

from legal_core.entities import ImposedSentence

from src.domain.fine_credit_review import set_fine_credit, validate_fine_credit
from src.domain.prepared_sentencing import PreparedSentencingInputs

CREDIT = {
    "scope": "final",
    "count_index": None,
    "original_amount": 10000,
    "reduced_amount": 5000,
    "released": False,
    "status": "stated",
}


class FineCreditReviewTest(unittest.TestCase):
    def test_correction_never_converts_days_or_changes_the_imposed_term(self):
        prepared = PreparedSentencingInputs(
            ImposedSentence(), guilt_by_count=(), aggregate_absorption=(False, False)
        )
        added = set_fine_credit(prepared, "new", CREDIT, "Синтетическая цитата")
        self.assertEqual(added.sentence.fine_credits[0].reduced_amount, 5000)
        self.assertIs(added.sentence.fine_credits[0].released, False)
        self.assertEqual(added.sentence.counts, ())
        unknown = set_fine_credit(added, "0", None, "")
        self.assertIn("fine_credit/0", unknown.unknown_fields)
        self.assertEqual(unknown.sentence.fine_credits, added.sentence.fine_credits)
        restored = set_fine_credit(
            unknown, "0", {**CREDIT, "released": True, "reduced_amount": 0}, "Освободить"
        )
        self.assertNotIn("fine_credit/0", restored.unknown_fields)
        self.assertIs(restored.sentence.fine_credits[0].released, True)

    def test_numbers_flags_scope_and_references_are_strict(self):
        for change in (
            {"released": 0},
            {"reduced_amount": True},
            {"original_amount": float("inf")},
            {"reduced_amount": float("nan")},
            {"reduced_amount": -1},
            {"reduced_amount": 20000},
            {"scope": "count", "count_index": True},
            {"scope": "final", "count_index": 0},
            {"released": True},
            {"status": "verified"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_fine_credit({**CREDIT, **change})
        prepared = PreparedSentencingInputs(None)
        with self.assertRaises(ValueError):
            set_fine_credit(
                prepared, "new", {**CREDIT, "scope": "count", "count_index": 0}, "Цитата"
            )
