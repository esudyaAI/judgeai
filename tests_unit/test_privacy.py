import unittest

from src.domain.privacy import (
    ExternalProcessingDenied,
    ExternalProcessingPolicy,
    IdentifierSpan,
    PrivacyRejected,
    PseudonymSession,
)


class PrivacyTests(unittest.TestCase):
    def test_repeated_value_round_trips_without_exposing_the_mapping(self):
        session = PseudonymSession("a" * 32)
        text = "Иванов и Иванов"
        masked = session.mask(text, (IdentifierSpan(0, 6), IdentifierSpan(9, 15)))
        self.assertNotIn("Иванов", masked)
        self.assertEqual(masked.split(" и ")[0], masked.split(" и ")[1])
        self.assertEqual(session.restore(masked), text)
        self.assertNotIn("Иванов", repr(session))

    def test_overlapping_spans_cover_the_union_and_preserve_original_text(self):
        session = PseudonymSession("b" * 32)
        text = "0123456789"
        masked = session.mask(text, (IdentifierSpan(2, 6), IdentifierSpan(4, 9)))
        self.assertTrue(masked.startswith("01["))
        self.assertTrue(masked.endswith("]9"))
        self.assertEqual(session.restore(masked), text)

    def test_forged_token_and_input_namespace_collision_are_rejected(self):
        session = PseudonymSession("c" * 32)
        with self.assertRaises(PrivacyRejected):
            session.restore("[JAI_" + "c" * 32 + "_999]")
        with self.assertRaises(PrivacyRejected):
            session.mask("[JAI_" + "c" * 32 + "_1]", ())
        with self.assertRaises(PrivacyRejected):
            session.mask("abc", (IdentifierSpan(0, 10),))

    def test_policy_requires_a_decision_and_the_exact_destination(self):
        for policy in [
            ExternalProcessingPolicy(None, ("https://example.invalid/v1",)),
            ExternalProcessingPolicy("decision-1", ()),
        ]:
            with self.assertRaises(ExternalProcessingDenied):
                policy.require("https://example.invalid/v1")
        policy = ExternalProcessingPolicy("decision-1", ("https://example.invalid/v1",))
        policy.require("https://example.invalid/v1/")
        with self.assertRaises(ExternalProcessingDenied):
            policy.require("https://other.invalid/v1")
