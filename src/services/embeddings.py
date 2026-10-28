import asyncio
import importlib
import time
from typing import Any

import httpx

from src.config import settings

# fastembed retries a failed download for about 40 s; without a pause every call (each file of
# an upload, each analysis) would wait that long again while the model source is unreachable.
LOAD_RETRY_SECONDS = 600.0

_model: Any = None
_failed_until = 0.0
_lock = asyncio.Lock()


class EmbeddingError(RuntimeError):
    """The embedding service could not be reached or returned something unusable."""


class JinaEmbeddings:
    """Jina cloud embeddings API (POST {base}/embeddings).

    Texts leave the server, so callers send only the anonymised fabula and public
    knowledge-base chunks (private chat uploads are never embedded). The key is sent in the
    Authorization header only and never appears in error messages.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        dimensions: int,
        base: str = "https://api.jina.ai/v1",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def embed(self, texts: list[str], task: str) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError("Jina не настроена: задайте JINA_API_KEY.")
        payload = {
            "model": self.model,
            "task": task,
            "dimensions": self.dimensions,
            "truncate": True,
            "input": texts,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base}/embeddings", json=payload, headers=headers
                )
                response.raise_for_status()
                rows = response.json()["data"]
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(f"Jina ответила {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"Ошибка обращения к Jina: {type(exc).__name__}") from exc
        try:
            ordered = sorted(rows, key=lambda row: row["index"])
            vectors = [[float(x) for x in row["embedding"]] for row in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError("Jina вернула ответ неожиданного вида") from exc
        if len(vectors) != len(texts):
            raise EmbeddingError("Jina вернула не столько векторов, сколько текстов")
        return vectors


def _jina() -> JinaEmbeddings:
    return JinaEmbeddings(
        settings.JINA_API_KEY,
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_DIM,
        settings.JINA_API_BASE,
        settings.EMBEDDING_TIMEOUT_SECONDS,
    )


def _clean_text(text: str, limit: int = 8000) -> str:
    return " ".join(text.split())[:limit]


def _requires_prefix() -> bool:
    return "e5" in settings.EMBEDDING_MODEL.lower()


async def get_embedding_model() -> Any:
    global _model, _failed_until

    if _model is None:
        async with _lock:
            if _model is None:
                if time.monotonic() < _failed_until:
                    raise RuntimeError("Embedding model unavailable after a failed load")
                try:
                    fastembed = importlib.import_module("fastembed")
                    text_embedding_cls = fastembed.TextEmbedding
                    _model = await asyncio.to_thread(
                        text_embedding_cls,
                        model_name=settings.EMBEDDING_MODEL,
                        cache_dir=settings.EMBEDDING_CACHE_DIR,
                    )
                except ModuleNotFoundError as exc:
                    raise RuntimeError(
                        "Пакет fastembed не установлен. Выполни: uv pip install fastembed"
                    ) from exc
                except Exception:
                    _failed_until = time.monotonic() + LOAD_RETRY_SECONDS
                    raise

    return _model


async def embed_texts(texts: list[str], prefix: str = "") -> list[list[float]]:
    if not texts:
        return []

    cleaned = [_clean_text(text) for text in texts]

    if prefix:
        cleaned = [f"{prefix} {text}" for text in cleaned]

    model = await get_embedding_model()

    def _embed() -> list[list[float]]:
        vectors = list(model.embed(cleaned))

        return [
            vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in vectors
        ]

    return await asyncio.to_thread(_embed)


async def embed_query(text: str) -> list[float] | None:
    if not text.strip():
        return None
    if settings.EMBEDDING_PROVIDER == "jina":
        return (await _jina().embed([_clean_text(text)], "retrieval.query"))[0]

    prefix = "query:" if _requires_prefix() else ""
    vectors = await embed_texts([text], prefix=prefix)

    return vectors[0] if vectors else None


async def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.EMBEDDING_PROVIDER == "jina":
        return await _jina().embed([_clean_text(text) for text in texts], "retrieval.passage")

    prefix = "passage:" if _requires_prefix() else ""
    return await embed_texts(texts, prefix=prefix)
