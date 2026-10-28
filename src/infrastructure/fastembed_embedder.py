"""Adapter: EmbeddingPort over the configured embeddings (local fastembed or Jina cloud)."""

from src.config import settings
from src.services.embeddings import embed_passages, embed_query


class FastembedEmbedder:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return await embed_passages(texts)

    async def embed_query(self, text: str) -> list[float] | None:
        return await embed_query(text)
