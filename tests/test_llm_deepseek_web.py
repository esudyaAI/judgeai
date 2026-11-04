"""DeepSeek web proxy adapter: single-message prompt, fresh conversation, tolerant JSON."""

import json

import httpx
import pytest

from src.services import llm_client
from src.services.llm_client import DeepSeekWebClient, LLMError, extract_json_object


def _reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _client(handler) -> DeepSeekWebClient:
    return DeepSeekWebClient(transport=httpx.MockTransport(handler))


async def test_system_prompt_is_folded_into_single_user_message():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(200, json={"reset": True})
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_reply('{"ok": true}'))

    result = await _client(handler).complete_json("ПРАВИЛА", "ДЕЛО")

    assert result == {"ok": True}
    body = seen[0]
    # The proxy forwards only the last message, so everything must be in one user turn.
    assert [m["role"] for m in body["messages"]] == ["user"]
    content = body["messages"][0]["content"]
    assert content.index("ПРАВИЛА") < content.index("ДЕЛО")
    assert "response_format" not in body


async def test_each_call_uses_new_conversation_and_resets_it():
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            calls.append(("DELETE", request.url.path.rsplit("/", 1)[-1]))
            return httpx.Response(200, json={"reset": True})
        calls.append(("POST", json.loads(request.content)["conversation_id"]))
        return httpx.Response(200, json=_reply('{"a": 1}'))

    client = _client(handler)
    await client.complete_json("s", "u1")
    await client.complete_json("s", "u2")

    posts = [cid for method, cid in calls if method == "POST"]
    deletes = [cid for method, cid in calls if method == "DELETE"]
    assert len(set(posts)) == 2, "two analyses must not share DeepSeek chat context"
    assert deletes == posts


async def test_reset_failure_does_not_lose_the_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(500)
        return httpx.Response(200, json=_reply('{"a": 1}'))

    assert await _client(handler).complete_json("s", "u") == {"a": 1}


async def test_proxy_error_is_reported_without_leaking_details():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "Can't create chat session."})

    with pytest.raises(LLMError, match="502"):
        await _client(handler).complete_json("s", "u")


async def test_transport_error_becomes_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMError, match="ConnectError"):
        await _client(handler).complete_json("s", "u")


async def test_non_json_answer_is_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_reply("Извините, не могу помочь."))

    with pytest.raises(LLMError, match="не JSON"):
        await _client(handler).complete_json("s", "u")


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Вот ответ:\n```\n{"a": 1}\n```\nГотово.',
        'Результат: {"a": 1} — конец.',
    ],
)
def test_extract_json_object_accepts_fences_and_prose(text):
    assert extract_json_object(text) == {"a": 1}


def test_extract_json_object_keeps_braces_inside_strings():
    assert extract_json_object('ок {"t": "скобка } внутри", "n": {"x": 2}}') == {
        "t": "скобка } внутри",
        "n": {"x": 2},
    }


@pytest.mark.parametrize("text", ["", "нет json", "[1, 2]", "{broken"])
def test_extract_json_object_rejects_non_objects(text):
    with pytest.raises(LLMError):
        extract_json_object(text)


def test_factory_selects_deepseek_web(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "deepseek_web")
    from src.services.external_processing import GuardedLLMClient

    client = llm_client.get_llm_client()
    assert isinstance(client, GuardedLLMClient)
    assert isinstance(client.backend, DeepSeekWebClient)
