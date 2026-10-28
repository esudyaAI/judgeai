"""Without a real language model the service reports an error instead of a sample verdict."""

import pytest

from src.services import llm_client
from src.services.llm_client import FakeLLMClient, LLMError, get_llm_client


def test_fake_provider_is_refused_unless_explicitly_allowed(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(llm_client.settings, "LLM_ALLOW_FAKE", False)
    with pytest.raises(LLMError, match="не подключена"):
        get_llm_client()


def test_fake_provider_works_only_with_the_test_flag(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(llm_client.settings, "LLM_ALLOW_FAKE", True)
    assert isinstance(get_llm_client(), FakeLLMClient)


def test_allow_fake_defaults_to_off():
    assert type(llm_client.settings).model_fields["LLM_ALLOW_FAKE"].default is False


async def test_analysis_without_llm_fails_and_shows_no_sample(client, monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(llm_client.settings, "LLM_ALLOW_FAKE", False)
    chat_id = (await client.post("/api/chats", json={"title": "без модели"})).json()["id"]
    r = await client.post(f"/api/chats/{chat_id}/messages", data={"content": "вопрос"})
    message_id = r.json()["assistant_message"]["id"]
    msg = (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()
    assert msg["status"] == "failed"
    assert msg["result"] is None
    assert "не подключена" in msg["error"]
    assert "ноутбук" not in str(msg)
