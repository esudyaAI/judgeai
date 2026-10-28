import unittest

from src.domain.conversation import DocumentContext, Turn, build_context


class ConversationTests(unittest.TestCase):
    def test_follow_up_keeps_history_documents_and_current_question_last(self):
        context = build_context(
            "Explain the sentence",
            [Turn("user", "Review verdict"), Turn("assistant", "Earlier assessment")],
            [DocumentContext("verdict.pdf", "Evidence from verdict", 3)],
        )
        self.assertIn("Review verdict", context.question)
        self.assertIn("Earlier assessment", context.question)
        self.assertTrue(context.question.endswith("Explain the sentence"))
        self.assertEqual(context.documents[0].text, "Evidence from verdict")
        self.assertEqual(context.documents[0].pages, 3)
        self.assertIn("not evidence", context.question)

    def test_empty_history_preserves_original_question(self):
        self.assertEqual(build_context(None, [], []).question, None)
        self.assertEqual(build_context("question", [], []).question, "question")

    def test_limits_keep_newest_whole_turns_and_documents_with_warning(self):
        context = build_context(
            "now",
            [Turn("user", "older"), Turn("user", "recent")],
            [DocumentContext("old.pdf", "X" * 20, 1), DocumentContext("new.pdf", "Y", 2)],
            history_chars=6,
            document_chars=2,
        )
        self.assertNotIn("older", context.question)
        self.assertIn("recent", context.question)
        self.assertEqual([d.name for d in context.documents], ["new.pdf"])
        self.assertTrue(context.warnings)

    def test_empty_document_is_not_counted(self):
        context = build_context("now", [], [DocumentContext("empty", "  ", 8)])
        self.assertEqual(context.documents, ())
