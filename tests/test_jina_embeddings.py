"""Jina cloud embeddings: request shape, task per role, order of results, errors."""

import json

import httpx
import pytest

from src.services import embeddings
from src.services.embeddings import EmbeddingError, JinaEmbeddings


def _transport(captured, status=200, data=None):
    def handler(request):
        captured.append(request)
        if status != 200:
            return httpx.Response(
                status, json={"detail": "x", "code": "RATE_REQUEST_LIMIT_EXCEEDED"}
            )
        body = json.loads(request.content)
        if data is not None:
            return httpx.Response(200, json=data)
        items = [{"index": i, "embedding": [float(i)] * 3} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(items))})

    return httpx.MockTransport(handler)


async def test_passages_use_retrieval_passage_task_and_keep_input_order():
    captured = []
    client = JinaEmbeddings(
        api_key="test-key",
        model="jina-embeddings-v3",
        dimensions=1024,
        transport=_transport(captured),
    )
    vectors = await client.embed(["первый", "второй"], task="retrieval.passage")
    assert vectors == [[0.0] * 3, [1.0] * 3]
    request = captured[0]
    assert str(request.url) == "https://api.jina.ai/v1/embeddings"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.content) == {
        "model": "jina-embeddings-v3",
        "task": "retrieval.passage",
        "dimensions": 1024,
        "truncate": True,
        "input": ["первый", "второй"],
    }


async def test_http_error_is_reported_without_the_key():
    client = JinaEmbeddings(
        api_key="secret-key", model="m", dimensions=8, transport=_transport([], status=429)
    )
    with pytest.raises(EmbeddingError) as error:
        await client.embed(["x"], task="retrieval.query")
    assert "429" in str(error.value)
    assert "secret-key" not in str(error.value)


async def test_missing_key_fails_before_any_request():
    captured = []
    client = JinaEmbeddings(api_key=None, model="m", dimensions=8, transport=_transport(captured))
    with pytest.raises(EmbeddingError, match="JINA_API_KEY"):
        await client.embed(["x"], task="retrieval.query")
    assert captured == []


@pytest.mark.parametrize("data", [{"data": []}, {"data": [{"index": 0}]}, {"rows": []}])
async def test_unexpected_response_is_an_error(data):
    client = JinaEmbeddings(
        api_key="k", model="m", dimensions=8, transport=_transport([], data=data)
    )
    with pytest.raises(EmbeddingError):
        await client.embed(["x"], task="retrieval.query")


async def test_jina_provider_routes_queries_and_passages(monkeypatch):
    calls = []

    async def fake_embed(self, texts, task):
        calls.append(task)
        return [[0.5] * 4 for _ in texts]

    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "jina")
    monkeypatch.setattr(JinaEmbeddings, "embed", fake_embed)
    assert await embeddings.embed_query("кража ноутбука") == [0.5] * 4
    assert await embeddings.embed_passages(["фабула"]) == [[0.5] * 4]
    assert calls == ["retrieval.query", "retrieval.passage"]
