import unittest
from unittest.mock import AsyncMock

from src.application.precedent_refresh import refresh_precedents
from src.application.similar_precedents import VerdictSource
from src.infrastructure.verdict_reader import PracticeReader


class PrecedentRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_never_writes(self):
        store = AsyncMock()
        store.stale_sources.return_value = [
            VerdictSource(
                1,
                "УСТАНОВИЛ:\nКража.\nПРИГОВОРИЛ:\nОсудить по ч. 1 ст. 158 УК РФ.",
                None,
                None,
                None,
                None,
            )
        ]
        report = await refresh_precedents(store, PracticeReader(), "new")
        self.assertTrue(report.dry_run)
        self.assertEqual(report.eligible_cards, 1)
        store.refresh_cards.assert_not_awaited()

    async def test_changed_card_shape_is_sent_to_review_instead_of_dropped(self):
        store = AsyncMock()
        store.stale_sources.return_value = [VerdictSource(1, "Текст", None, None, None, None)]
        store.refresh_cards.return_value = None
        report = await refresh_precedents(store, PracticeReader(), "new", apply=True)
        self.assertEqual(report.updated_cards, 0)
        self.assertEqual(report.needs_review, 1)

    async def test_dry_run_reports_unsafe_shape_without_any_write(self):
        store = AsyncMock()
        store.stale_sources.return_value = [VerdictSource(1, "Текст", None, None, None, None)]
        store.can_refresh.return_value = False
        report = await refresh_precedents(store, PracticeReader(), "precedent-card/3")
        self.assertEqual(report.eligible_cards, 0)
        self.assertEqual(report.needs_review, 1)
        store.refresh_cards.assert_not_awaited()
