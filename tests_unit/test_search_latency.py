"""Search regressions with deterministic ports, no providers or database."""

import asyncio
import unittest
from dataclasses import replace

from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification, Recidivism

from src.application.practice_report import compare_draft_with_practice
from src.application.similar_precedents import FindSimilarPrecedents, StoredCard
from src.infrastructure.bounded_embedder import BoundedQueryEmbedder


def card():
    return PrecedentCard(
        (PrecedentEpisode(Qualification("158", 2)), PrecedentEpisode(Qualification("161", 1))),
        frozenset({"61.1.г"}),
        frozenset(),
        Recidivism.NONE,
        frozenset(),
        None,
        False,
        "Подсудимый тайно похитил имущество, имеет малолетнего ребёнка.",
    )


class MemoryStore:
    def __init__(self):
        self.value = StoredCard(1, card(), 1, None, None, None, None)

    async def vector_channel(self, vector, model, article, limit):
        return [(1, 0.9)]

    async def qualification_channel(self, keys, limit):
        return [1]

    async def fulltext_channel(self, text, limit):
        return [1]

    async def load(self, ids):
        return {1: self.value} if 1 in ids else {}


class CountingEmbedder:
    model_name = "test-only"

    def __init__(self):
        self.texts = []

    async def embed_query(self, text):
        self.texts.append(text)
        return [1.0, 0.0]


class SearchLatencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_vector_per_fabula_keeps_both_episode_results(self):
        embedder = CountingEmbedder()
        report = await compare_draft_with_practice(MemoryStore(), embedder, card())
        self.assertEqual(len(report.episodes), 2)
        self.assertTrue(all(r.shown and r.vector_used for r in report.episodes))
        self.assertEqual(len(embedder.texts), 1)

    async def test_failed_provider_is_not_retried_for_every_count(self):
        class Broken(CountingEmbedder):
            async def embed_query(self, text):
                self.texts.append(text)
                raise RuntimeError("synthetic provider outage")

        embedder = Broken()
        report = await compare_draft_with_practice(MemoryStore(), embedder, card())
        self.assertTrue(all(r.shown and not r.vector_used for r in report.episodes))
        self.assertEqual(len(embedder.texts), 1)

    async def test_timeout_cancels_provider_and_keeps_other_channels(self):
        cancelled = asyncio.Event()

        class Hung(CountingEmbedder):
            async def embed_query(self, text):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        search = FindSimilarPrecedents(MemoryStore(), BoundedQueryEmbedder(Hung(), timeout=0.01))
        result = await asyncio.wait_for(search.execute(card()), timeout=1)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(result.vector_used)
        self.assertEqual([r.stored.id for r in result.items], [1])
        self.assertEqual(result.items[0].channels, ("qualification", "fulltext"))

    async def test_different_text_and_separate_reports_never_share_cached_vectors(self):
        embedder = CountingEmbedder()
        search = FindSimilarPrecedents(MemoryStore(), embedder)
        await search.execute(card())
        await search.execute(replace(card(), fabula="Другая фабула преступления."))
        await compare_draft_with_practice(MemoryStore(), embedder, card())
        self.assertEqual(len(embedder.texts), 3)

    async def test_external_cancellation_is_not_replaced_by_fallback(self):
        entered = asyncio.Event()

        class Hung(CountingEmbedder):
            async def embed_query(self, text):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(FindSimilarPrecedents(MemoryStore(), Hung()).execute(card()))
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_query_deadline_does_not_cut_off_offline_batch_embedding(self):
        class SlowBatch(CountingEmbedder):
            async def embed_passages(self, texts):
                await asyncio.sleep(0.02)
                return [[float(len(text))] for text in texts]

        embedder = BoundedQueryEmbedder(SlowBatch(), timeout=0.001)
        vectors = await embedder.embed_passages(["one", "second"])
        self.assertEqual(vectors, [[3.0], [6.0]])
