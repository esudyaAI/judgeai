import unittest

from src.domain.extraction import input_hash
from src.domain.review_evidence import (
    Evidence,
    InvalidEvidence,
    ReviewDocument,
    ReviewSources,
    SourceFingerprint,
    SourceRange,
    SubjectSource,
    validate_evidence,
)


class EvidenceTests(unittest.TestCase):
    def context(self):
        text = "😀 ФИО1: два года. ФИО2: два года."
        start = text.index("ФИО2")
        document = ReviewDocument(0, "synthetic.txt", text)
        context = ReviewSources(
            (SourceFingerprint(0, input_hash(text)),),
            (
                SubjectSource(0, "ФИО1", (SourceRange(0, 0, start),)),
                SubjectSource(1, "ФИО2", (SourceRange(0, start, len(text)),)),
            ),
        )
        return (document,), context

    def test_exact_unicode_coordinates_and_hash_are_required(self):
        documents, context = self.context()
        text = documents[0].text
        start = text.index("два года")
        evidence = Evidence(0, input_hash(text), start, start + 8, "два года")
        validate_evidence(documents, context, 0, evidence)
        for invalid in (
            Evidence(0, "0" * 64, start, start + 8, "два года"),
            Evidence(0, input_hash(text), start + 1, start + 9, "два года"),
            Evidence(0, input_hash(text), start, start + 8, "Два года"),
            Evidence(True, input_hash(text), start, start + 8, "два года"),
        ):
            with self.assertRaises(InvalidEvidence):
                validate_evidence(documents, context, 0, invalid)

    def test_identical_words_from_another_person_do_not_match_by_position(self):
        documents, context = self.context()
        text = documents[0].text
        start = text.rindex("два года")
        evidence = Evidence(0, input_hash(text), start, start + 8, "два года")
        validate_evidence(documents, context, 1, evidence)
        with self.assertRaises(InvalidEvidence):
            validate_evidence(documents, context, 0, evidence)

    def test_boolean_subject_is_not_a_person_index(self):
        documents, context = self.context()
        text = documents[0].text
        start = text.rindex("два года")
        with self.assertRaises(InvalidEvidence):
            validate_evidence(
                documents,
                context,
                True,
                Evidence(0, input_hash(text), start, start + 8, "два года"),
            )
