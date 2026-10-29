"""Jina rate limits and outages are retried with a pause; chunk re-embedding is opt-in."""

import json

import httpx
import pytest

from src.cli import precedents as cli
from src.services import embeddings
from src.services.embeddings import EmbeddingError, JinaEmbeddings


def _ok(n=1):
    return httpx.Response(200, json={"data": [{"index": i, "embedding": [1.0]} for i in range(n)]})


@pytest.fixture
def pauses(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(embeddings, "_sleep", fake_sleep)
    return slept


def _client(responses, requests):
    def handler(request):
        requests.append(json.loads(request.content))
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return JinaEmbeddings(
        api_key="k", model="m", dimensions=4, transport=httpx.MockTransport(handler)
    )


async def test_rate_limit_is_retried_honouring_retry_after(pauses):
    requests = []
    client = _client([httpx.Response(429, headers={"Retry-After": "7"}), _ok()], requests)
    assert await client.embed(["x"], task="retrieval.passage") == [[1.0]]
    assert len(requests) == 2 and pauses == [7.0]


async def test_outage_and_network_errors_are_retried(pauses):
    client = _client([httpx.Response(503), httpx.ConnectError("down"), _ok()], [])
    assert await client.embed(["x"], task="retrieval.passage") == [[1.0]]
    assert pauses == [2.0, 4.0]


async def test_gives_up_after_the_last_attempt(pauses):
    requests = []
    attempts = embeddings.JINA_ATTEMPTS
    client = _client([httpx.Response(429) for _ in range(attempts)], requests)
    with pytest.raises(EmbeddingError, match="429.*лимит"):
        await client.embed(["x"], task="retrieval.passage")
    assert len(requests) == attempts and len(pauses) == attempts - 1


async def test_client_errors_are_not_retried(pauses):
    requests = []
    client = _client([httpx.Response(401)], requests)
    with pytest.raises(EmbeddingError, match="401"):
        await client.embed(["x"], task="retrieval.passage")
    assert len(requests) == 1 and pauses == []


class _NoVectors:
    model_name = "test-model"

    async def embed_passages(self, texts):
        return [[1.0] for _ in texts]

    async def embed_query(self, text):
        return [1.0]


async def test_index_skips_knowledge_chunks_unless_asked(monkeypatch):
    calls = []

    async def fake_reembed():
        calls.append(1)
        return 0

    monkeypatch.setattr(cli, "_reembed_chunks", fake_reembed)
    report = await cli.run_index(embedder=_NoVectors())
    assert "knowledge_chunks" not in report and calls == []
    report = await cli.run_index(embedder=_NoVectors(), chunks=True)
    assert report["knowledge_chunks"] == 0 and calls == [1]
