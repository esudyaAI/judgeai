"""Bound interactive query latency without changing offline embedding retries."""

import asyncio

from src.application.similar_precedents import EmbeddingPort


class BoundedQueryEmbedder:
    def __init__(self, embedder: EmbeddingPort, timeout: float = 10.0):
        self.embedder = embedder
        self.model_name = embedder.model_name
        self.timeout = timeout

    async def embed_query(self, text: str) -> list[float] | None:
        # Cancellation closes async HTTP clients, including retry sleeps. A local model
        # loading in a worker thread may finish in the background after this deadline.
        async with asyncio.timeout(self.timeout):
            return await self.embedder.embed_query(text)

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return await self.embedder.embed_passages(texts)
