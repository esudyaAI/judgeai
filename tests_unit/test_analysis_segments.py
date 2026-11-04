import unittest

from src.domain.analysis_segments import segment_documents
from src.domain.extraction import input_hash


class AnalysisSegmentsTests(unittest.TestCase):
    def test_every_character_and_source_coordinate_is_preserved(self):
        texts = ["  начало\n" + "середина " * 9000 + "\nконец  ", "второй документ"]
        segments = segment_documents(texts)
        for document_index, text in enumerate(texts):
            own = [s for s in segments if s.document_index == document_index]
            covered = set()
            for s in own:
                self.assertEqual(s.text, text[s.start : s.end])
                self.assertEqual(s.document_hash, input_hash(text))
                self.assertLessEqual(len(s.text), 28000)
                covered.update(range(s.start, s.end))
            self.assertEqual(covered, set(range(len(text))))

    def test_overlap_keeps_boundary_quote_in_at_least_one_segment(self):
        text = "a" * 27500 + "ЦИТАТА" * 150 + "b" * 10000
        segments = segment_documents([text])
        self.assertNotIn("ЦИТАТА" * 150, segments[0].text)
        self.assertIn("ЦИТАТА" * 150, segments[1].text)
        self.assertLess(segments[1].start, segments[0].end)

    def test_empty_documents_and_invalid_limits(self):
        self.assertEqual(segment_documents(["", "  "]), ())
        for limit, overlap in [(0, 0), (20, 20), (20, -1)]:
            with self.assertRaises(ValueError):
                segment_documents(["abc"], max_chars=limit, overlap=overlap)

    def test_exact_limit_needs_only_one_segment(self):
        segments = segment_documents(["x" * 100], max_chars=100, overlap=10)
        self.assertEqual(len(segments), 1)
        self.assertEqual((segments[0].start, segments[0].end), (0, 100))


class ProtectedBoundaryTests(unittest.TestCase):
    def test_an_identifier_is_not_cut_at_either_edge(self):
        from src.domain.privacy import IdentifierSpan

        text = "a" * 27500 + "X" * 900 + "b" * 10000
        protected = ((IdentifierSpan(27500, 28400),),)
        windows = segment_documents([text], protected=protected)
        for window in windows:
            self.assertFalse(27500 < window.start < 28400)
            self.assertFalse(27500 < window.end < 28400)
        self.assertTrue(any("X" * 900 in window.text for window in windows))
        self.assertEqual(
            set().union(*(set(range(w.start, w.end)) for w in windows)), set(range(len(text)))
        )
