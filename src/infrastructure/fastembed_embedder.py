"""Adapter: EmbeddingPort over the configured embeddings (local fastembed or Jina cloud)."""

from src.application.similar_precedents import EmbeddingPort
from src.services.embeddings import embed_passages, embed_query, embedding_cache_model


class FastembedEmbedder:
    def __init__(self, model_name: str | None = None, materials: tuple[str, ...] = ()):
        self._model_override = model_name
        self.materials = materials
        self.model_name = embedding_cache_model(model_name)

    def with_materials(self, materials: tuple[str, ...]):
        return FastembedEmbedder(self._model_override, materials)

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return (
            await embed_passages(texts, materials=self.materials)
            if self.materials
            else await embed_passages(texts)
        )

    async def embed_query(self, text: str) -> list[float] | None:
        return (
            await embed_query(text, materials=self.materials)
            if self.materials
            else await embed_query(text)
        )


def with_embedding_materials(embedder: EmbeddingPort, materials: tuple[str, ...]) -> EmbeddingPort:
    bind = getattr(embedder, "with_materials", None)
    return bind(materials) if callable(bind) else embedder
