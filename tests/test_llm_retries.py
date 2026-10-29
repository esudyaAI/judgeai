"""Transient model failures (429, 5xx, timeouts) are retried with a pause; others are not."""

import json

import httpx
import pytest

from src.services import llm_client
from src.services.llm_client import LLMError, OpenAICompatibleClient


def _ok() -> httpx.Response:
    content = json.dumps({"answer": 4})
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture
def pauses(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(llm_client, "_sleep", fake_sleep)
    monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "test-key")
    return slept


def _client(responses: list, requests: list) -> OpenAICompatibleClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return OpenAICompatibleClient(transport=httpx.MockTransport(handler))


async def test_503_is_retried_and_the_answer_returned(pauses):
    requests: list = []
    client = _client([httpx.Response(503), _ok()], requests)
    assert await client.complete_json("s", "u") == {"answer": 4}
    assert len(requests) == 2
    assert pauses == [2.0]


async def test_429_honours_retry_after(pauses):
    requests: list = []
    client = _client([httpx.Response(429, headers={"Retry-After": "5"}), _ok()], requests)
    assert await client.complete_json("s", "u") == {"answer": 4}
    assert pauses == [5.0]


async def test_retry_after_is_capped(pauses):
    client = _client([httpx.Response(429, headers={"Retry-After": "3600"}), _ok()], [])
    await client.complete_json("s", "u")
    assert pauses == [llm_client.MAX_RETRY_PAUSE_SECONDS]


async def test_gives_up_after_the_last_attempt_with_a_clear_message(pauses):
    requests: list = []
    client = _client([httpx.Response(503) for _ in range(llm_client.LLM_ATTEMPTS)], requests)
    with pytest.raises(LLMError) as error:
        await client.complete_json("s", "u")
    assert len(requests) == llm_client.LLM_ATTEMPTS
    assert pauses == [2.0, 4.0, 8.0][: llm_client.LLM_ATTEMPTS - 1]
    assert "503" in str(error.value) and "временно недоступна" in str(error.value)


async def test_rate_limit_message_after_retries(pauses):
    client = _client([httpx.Response(429) for _ in range(llm_client.LLM_ATTEMPTS)], [])
    with pytest.raises(LLMError, match="429.*лимит"):
        await client.complete_json("s", "u")


async def test_client_errors_are_not_retried(pauses):
    requests: list = []
    client = _client([httpx.Response(400)], requests)
    with pytest.raises(LLMError, match="LLM ответил 400"):
        await client.complete_json("s", "u")
    assert len(requests) == 1 and pauses == []


async def test_connection_errors_are_retried(pauses):
    requests: list = []
    client = _client([httpx.ConnectError("down"), _ok()], requests)
    assert await client.complete_json("s", "u") == {"answer": 4}
    assert len(requests) == 2


async def test_user_prompt_guarantees_json_word_for_json_object_format(pauses):
    requests: list = []
    client = _client([_ok()], requests)
    await client.complete_json("система", "вопрос без специального слова")
    body = json.loads(requests[0].content)
    user_msg = body["messages"][1]["content"]
    assert "Ответь в формате JSON." in user_msg
    assert "json" in user_msg.lower()


async def test_user_prompt_preserves_existing_json_word(pauses):
    requests: list = []
    client = _client([_ok()], requests)
    await client.complete_json("система", "верни ответ в JSON формате")
    body = json.loads(requests[0].content)
    user_msg = body["messages"][1]["content"]
    assert user_msg == "верни ответ в JSON формате"


async def test_error_status_logs_response_text(pauses, caplog):
    import logging

    requests: list = []
    error_body = '{"error": {"message": "invalid request", "code": "invalid_request"}}'
    client = _client([httpx.Response(400, text=error_body)], requests)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(LLMError):
            await client.complete_json("s", "u")

    assert any(
        "LLM API error 400" in record.message and "invalid request" in record.message
        for record in caplog.records
    )
