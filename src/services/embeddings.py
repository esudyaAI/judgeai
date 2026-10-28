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


# Jina rate limits (429) and outages (5xx, network) are retried with a growing pause; a
# Retry-After header is honoured up to a cap. Other errors fail at once.
JINA_ATTEMPTS = 5
JINA_PAUSES_SECONDS = (2.0, 4.0, 8.0, 16.0)
JINA_MAX_PAUSE_SECONDS = 60.0
JINA_RETRYABLE = {429, 500, 502, 503, 504}
_sleep = asyncio.sleep


def _jina_pause(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        try:
            requested = float(response.headers.get("Retry-After", ""))
        except ValueError:
            requested = None
        if requested is not None and requested >= 0:
            return min(requested, JINA_MAX_PAUSE_SECONDS)
    return JINA_PAUSES_SECONDS[min(attempt, len(JINA_PAUSES_SECONDS) - 1)]


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
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for attempt in range(JINA_ATTEMPTS):
                last = attempt == JINA_ATTEMPTS - 1
                try:
                    response = await client.post(
                        f"{self.base}/embeddings", json=payload, headers=headers
                    )
                except httpx.TransportError as exc:  # connection refused, timeout, reset
                    if last:
                        raise EmbeddingError(
                            f"Ошибка обращения к Jina: {type(exc).__name__}"
                        ) from exc
                    await _sleep(_jina_pause(attempt, None))
                    continue
                status = response.status_code
                if status in JINA_RETRYABLE and not last:
                    await _sleep(_jina_pause(attempt, response))
                    continue
                if status == 429:
                    raise EmbeddingError("Jina ответила 429: превышен лимит запросов или токенов")
                if status >= 400:
                    raise EmbeddingError(f"Jina ответила {status}")
                try:
                    rows = response.json()["data"]
                except (KeyError, TypeError, ValueError) as exc:
                    raise EmbeddingError("Jina вернула ответ неожиданного вида") from exc
                break
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
