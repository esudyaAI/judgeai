"""Tests for the fallback LLM client (OpenAI primary -> DeepSeek web proxy fallback)."""

import json

import httpx
import pytest

from src.services import llm_client
from src.services.llm_client import (
    DeepSeekWebClient,
    FallbackLLMClient,
    LLMError,
    OpenAICompatibleClient,
    get_llm_client,
)


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _openai_json(data: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(data)}}]}


async def test_primary_success_does_not_invoke_fallback():
    fallback_called = False

    class FakePrimary:
        async def complete_json(self, system: str, user: str) -> dict:
            return {"source": "primary"}

    class FakeFallback:
        async def complete_json(self, system: str, user: str) -> dict:
            nonlocal fallback_called
            fallback_called = True
            return {"source": "fallback"}

    client = FallbackLLMClient(primary=FakePrimary(), fallback=FakeFallback())
    result = await client.complete_json("sys", "user")

    assert result == {"source": "primary"}
    assert fallback_called is False


async def test_primary_failure_invokes_fallback():
    class FakePrimary:
        async def complete_json(self, system: str, user: str) -> dict:
            raise LLMError("LLM ответил 429: превышен лимит запросов")

    class FakeFallback:
        async def complete_json(self, system: str, user: str) -> dict:
            return {"source": "fallback"}

    client = FallbackLLMClient(primary=FakePrimary(), fallback=FakeFallback())
    result = await client.complete_json("sys", "user")

    assert result == {"source": "fallback"}


async def test_primary_missing_api_key_invokes_fallback():
    # OpenAI client without API key raises LLMError
    primary = OpenAICompatibleClient(api_key="")

    class FakeFallback:
        async def complete_json(self, system: str, user: str) -> dict:
            return {"recovered": True}

    client = FallbackLLMClient(primary=primary, fallback=FakeFallback())
    result = await client.complete_json("sys", "user")

    assert result == {"recovered": True}


async def test_both_primary_and_fallback_failing_raises_combined_error():
    class FakePrimary:
        async def complete_json(self, system: str, user: str) -> dict:
            raise LLMError("OpenAI gateway 502")

    class FakeFallback:
        async def complete_json(self, system: str, user: str) -> dict:
            raise LLMError("DeepSeek web 504")

    client = FallbackLLMClient(primary=FakePrimary(), fallback=FakeFallback())
    with pytest.raises(LLMError) as exc_info:
        await client.complete_json("sys", "user")

    msg = str(exc_info.value)
    assert "OpenAI gateway 502" in msg
    assert "DeepSeek web 504" in msg


async def test_integration_primary_http_429_falls_back_to_deepseek_web(monkeypatch):
    async def fake_sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(llm_client, "_sleep", fake_sleep)

    def primary_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit exceeded"})

    def fallback_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, json={"reset": True})
        return httpx.Response(200, json=_reply('{"source": "deepseek_fallback"}'))

    primary = OpenAICompatibleClient(
        api_key="test-key",
        api_base="https://api.primary.com/v1",
        transport=httpx.MockTransport(primary_handler),
    )
    fallback = DeepSeekWebClient(
        api_base="http://localhost:28080/v1",
        transport=httpx.MockTransport(fallback_handler),
    )

    client = FallbackLLMClient(primary=primary, fallback=fallback)
    result = await client.complete_json("sys", "user")

    assert result == {"source": "deepseek_fallback"}


def test_factory_selects_fallback_by_default(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_client.settings, "LLM_FALLBACK_PROVIDER", "deepseek_web")
    client = get_llm_client()
    assert isinstance(client, FallbackLLMClient)
    assert isinstance(client.primary, OpenAICompatibleClient)
    assert isinstance(client.fallback, DeepSeekWebClient)


def test_factory_fallback_disabled_returns_openai_client(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_client.settings, "LLM_FALLBACK_PROVIDER", "none")
    client = get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)


def test_factory_explicit_fallback_provider(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "fallback")
    monkeypatch.setattr(llm_client.settings, "LLM_FALLBACK_PROVIDER", "deepseek_web")
    client = get_llm_client()
    assert isinstance(client, FallbackLLMClient)


def test_deepseek_web_uses_fallback_settings():
    client = DeepSeekWebClient(
        api_base="http://custom-proxy:28080/v1",
        model="custom-deepseek",
        api_key="custom-key",
    )
    assert client._api_base == "http://custom-proxy:28080/v1"
    assert client._model == "custom-deepseek"
    assert client._api_key == "custom-key"
