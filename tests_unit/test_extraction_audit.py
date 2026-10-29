import unittest
from dataclasses import replace

from src.application.extraction_audit import AuditSource, audit_source, audit_sources
from src.infrastructure.verdict_reader import PracticeReader

TEXT = "ПРИГОВОР\nУСТАНОВИЛ:\nСовершена кража.\nПРИГОВОРИЛ:\nОсудить по ч. 1 ст. 158 УК РФ."


class ExtractionAuditTests(unittest.TestCase):
    def source(self, **changes):
        return replace(
            AuditSource("case-1", TEXT, "sudact", "https://example.test/case"), **changes
        )

    def test_missing_is_never_silently_called_absent(self):
        result = audit_source(PracticeReader(), self.source())
        missing = [
            field for card in result.cards for field in card.fields if field.status != "present"
        ]
        self.assertTrue(missing)
        self.assertTrue(all(field.status == "needs_review" for field in missing))
        self.assertIn("recidivism", [field.name for field in missing])

    def test_private_sources_are_not_read_or_quoted(self):
        class Forbidden:
            def read_all(self, text):
                raise AssertionError("private source was read")

        result = audit_source(Forbidden(), self.source(source_type="chat"))
        self.assertEqual(result.status, "skipped_private")
        self.assertEqual(result.cards, ())

    def test_reader_failure_is_accounted_for_and_does_not_drop_other_cases(self):
        class Broken(PracticeReader):
            def read_all(self, text):
                if text == "broken":
                    raise ValueError("must not leak the document in logs")
                return super().read_all(text)

        report = audit_sources(Broken(), [self.source(text="broken"), self.source(key="case-2")])
        self.assertEqual(report.summary["sources"], 2)
        self.assertEqual(report.summary["errors"], 1)
        self.assertEqual(report.summary["read"], 1)
        self.assertEqual(report.documents[0].error, "ValueError")

    def test_quotes_are_opt_in_and_hash_is_of_actual_input(self):
        plain = audit_source(PracticeReader(), self.source())
        quoted = audit_source(PracticeReader(), self.source(), include_quotes=True)
        self.assertTrue(plain.text_hash)
        self.assertTrue(all(not f.quote for c in plain.cards for f in c.fields))
        self.assertTrue(any(f.quote for c in quoted.cards for f in c.fields))

    def test_no_cards_is_distinguished_from_unreadable_or_empty(self):
        class NoPractice:
            def read_all(self, text):
                return []

        self.assertEqual(audit_source(NoPractice(), self.source()).status, "no_cards")
        self.assertEqual(audit_source(PracticeReader(), self.source(text="")).status, "empty")
