import unittest

from src.domain.cited_facts import CitedCandidate, merge_candidates


def candidate(value, path=("history_complete",), start=0):
    return CitedCandidate(path, value, "источник", 0, "digest", start, start + 8)


class MergeCandidatesTests(unittest.TestCase):
    def test_equal_values_keep_one_input(self):
        first = candidate(True)
        result = merge_candidates((first, candidate(True, start=9)))
        self.assertEqual(result.accepted, (first,))
        self.assertEqual(result.conflicts, ())

    def test_conflicts_are_explicit_and_do_not_produce_an_accepted_value(self):
        result = merge_candidates((candidate(True), candidate(False)))
        self.assertEqual(result.accepted, ())
        self.assertEqual(result.conflicts, (("history_complete",),))

    def test_boolean_is_not_integer_and_distinct_paths_are_independent(self):
        result = merge_candidates((candidate(True), candidate(1), candidate("other", ("guilt",))))
        self.assertEqual([c.path for c in result.accepted], [("guilt",)])
        self.assertEqual(len(result.conflicts), 1)


class SegmentHistoryTests(unittest.TestCase):
    def test_missing_or_rejected_prior_blocks_global_complete_history(self):
        from src.domain.cited_facts import SegmentFacts, merge_segment_facts

        complete = SegmentFacts("one", (candidate(True),))
        missing = SegmentFacts("two")
        result = merge_segment_facts((complete, missing))
        self.assertEqual(result.accepted, ())
        rejected = SegmentFacts("two", (candidate(True),), ("prior_convictions / judgment_id",))
        self.assertEqual(merge_segment_facts((complete, rejected)).accepted, ())
        self.assertEqual(len(merge_segment_facts((complete, complete)).accepted), 1)
