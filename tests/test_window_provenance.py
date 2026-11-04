import json

import httpx
from sqlalchemy import select

from src.db.llm_window_extractions import PrivateLlmWindowExtraction
from src.db.models import Chat
from src.db.session import async_session_factory
from src.domain.privacy import ExternalProcessingPolicy
from src.services.external_processing import GuardedLLMClient
from src.services.llm_client import OpenAICompatibleClient
from src.services.punishment_window_resolver import (
    FIELD,
    PROMPT_VERSION,
    resolve_windows,
    window_hash,
)
from tests.test_auth import account
from tests.test_punishment_window_resolver import WINDOW, CountingLlm

BASE = "https://synthetic.invalid/v1"


def guarded(model, requests):
    def handle(request):
        requests.append(json.loads(request.content))
        answer = {"kind": "imprisonment", "years": 2, "quote": "лишения свободы"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    return GuardedLLMClient(
        OpenAICompatibleClient(
            api_base=BASE,
            api_key="synthetic-secret",
            model=model,
            transport=httpx.MockTransport(handle),
        ),
        BASE,
        ExternalProcessingPolicy("synthetic-approval", (BASE,)),
    )


async def test_cache_hit_keeps_original_model_receipt_after_client_changes():
    owner = await account("window-provenance")
    requests, first_audit, second_audit = [], [], []
    async with async_session_factory() as db:
        chat = Chat(owner_id=owner, title="synthetic")
        db.add(chat)
        await db.commit()
        first = await resolve_windows(
            db, guarded("original-model", requests), (WINDOW,), chat_id=chat.id, audit=first_audit
        )
        second = await resolve_windows(
            db, guarded("later-model", requests), (WINDOW,), chat_id=chat.id, audit=second_audit
        )
        row = await db.scalar(select(PrivateLlmWindowExtraction))
        assert row.provenance == first_audit[0]["provenance"]
    assert first == second and first[0][1].amount == 24
    assert len(requests) == 1
    assert first_audit[0]["cache_hit"] is False and second_audit[0]["cache_hit"] is True
    assert first_audit[0]["provenance"] == second_audit[0]["provenance"]
    assert second_audit[0]["provenance"]["llm"]["calls"][0]["requested_model"] == "original-model"
    assert "synthetic-secret" not in str(second_audit) and BASE not in str(second_audit)


async def test_legacy_cache_provenance_stays_unknown_without_network():
    owner = await account("window-legacy")
    audit = []
    llm = CountingLlm(RuntimeError("must not call provider"))
    async with async_session_factory() as db:
        chat = Chat(owner_id=owner, title="synthetic")
        db.add(chat)
        await db.flush()
        db.add(
            PrivateLlmWindowExtraction(
                chat_id=chat.id,
                input_hash=window_hash(WINDOW),
                field=FIELD,
                prompt_version=PROMPT_VERSION,
                value={"kind": "imprisonment", "years": 2, "quote": "лишения свободы"},
            )
        )
        await db.commit()
        result = await resolve_windows(db, llm, (WINDOW,), chat_id=chat.id, audit=audit)
    assert result[0][1].amount == 24 and llm.calls == 0
    assert audit[0]["cache_hit"] and audit[0]["provenance"] is None


async def test_concurrent_window_receipts_are_isolated_per_task():
    import asyncio

    from src.services.llm_receipts import record_receipt

    class Concurrent:
        async def complete_json(self, system, user):
            await asyncio.sleep(0.02 if user.endswith("first") else 0)
            record_receipt({"synthetic_window": user.rsplit(" ", 1)[-1]})
            return {"kind": "imprisonment", "years": 2, "quote": "лишения свободы"}

    audit = []
    async with async_session_factory() as db:
        await resolve_windows(
            db, Concurrent(), (WINDOW + " first", WINDOW + " second"), audit=audit
        )
    assert [entry["provenance"]["llm"]["calls"] for entry in audit] == [
        [{"synthetic_window": "first"}],
        [{"synthetic_window": "second"}],
    ]


async def test_api_report_keeps_cached_model_and_marks_unknown_legacy(client, monkeypatch):
    import io
    from zipfile import ZipFile

    from src.services import analysis_runner
    from src.services.punishment_window_resolver import SYSTEM_PROMPT

    source = "ПРИГОВОР\nУСТАНОВИЛ:\nСинтетическое описание.\nПРИГОВОРИЛ:\n" + WINDOW
    requests = []

    def factory(model):
        def handle(request):
            body = json.loads(request.content)
            requests.append(body)
            is_window = body["messages"][0]["content"].startswith(SYSTEM_PROMPT)
            answer = (
                {"kind": "imprisonment", "years": 2, "quote": "лишения свободы"}
                if is_window
                else {"fabula": "Синтетический результат"}
            )
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(answer)}}]}
            )

        return GuardedLLMClient(
            OpenAICompatibleClient(
                api_base=BASE,
                api_key="synthetic-secret",
                model=model,
                transport=httpx.MockTransport(handle),
            ),
            BASE,
            ExternalProcessingPolicy("synthetic-only", (BASE,)),
        )

    monkeypatch.setattr(analysis_runner.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(analysis_runner, "get_llm_client", lambda: factory("original-window-model"))
    chat = (await client.post("/api/chats", json={"title": "synthetic"})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "Проверь"},
        files=[("files", ("synthetic.txt", source.encode(), "text/plain"))],
    )
    message = sent.json()["assistant_message"]["id"]
    first = (await client.get(f"/api/chats/{chat}/messages/{message}")).json()
    assert first["status"] == "completed", first
    windows = first["result"]["provenance"]["window_readings"]
    assert len(windows) == 1 and windows[0]["cache_hit"] is False
    report = (await client.post(f"/api/chats/{chat}/messages/{message}/reports")).json()
    url = f"/api/reports/{report['id']}"
    snapshot = (await client.get(url)).json()
    artifact = (await client.get(url + "/docx")).content
    with ZipFile(io.BytesIO(artifact)) as document:
        assert "original-window-model" in document.read("word/document.xml").decode()
    monkeypatch.setattr(analysis_runner, "get_llm_client", lambda: factory("later-facts-model"))
    second = await client.post(f"/api/chats/{chat}/messages", data={"content": "Проверь снова"})
    second_id = second.json()["assistant_message"]["id"]
    reply = (await client.get(f"/api/chats/{chat}/messages/{second_id}")).json()
    assert reply["status"] == "completed", reply
    audit = reply["result"]["provenance"]["window_readings"][0]
    assert audit["cache_hit"] is True and audit["provenance"] == windows[0]["provenance"]
    assert (
        reply["result"]["provenance"]["llm"]["calls"][0]["requested_model"] == "later-facts-model"
    )
    async with async_session_factory() as db:
        row = await db.scalar(select(PrivateLlmWindowExtraction))
        row.provenance = None
        await db.commit()
    third = await client.post(f"/api/chats/{chat}/messages", data={"content": "Ещё проверка"})
    third_id = third.json()["assistant_message"]["id"]
    legacy = (await client.get(f"/api/chats/{chat}/messages/{third_id}")).json()["result"]
    assert legacy["provenance"]["window_readings"][0]["provenance"] is None
    assert any("не сохранены" in item for item in legacy["provenance"]["limitations"])
    assert (await client.get(url)).json() == snapshot
    assert (await client.get(url + "/docx")).content == artifact
    window_calls = [r for r in requests if r["messages"][0]["content"].startswith(SYSTEM_PROMPT)]
    assert len(window_calls) == 1


async def test_fallback_receipt_attributes_only_the_successful_provider(monkeypatch):
    from src.services import llm_client
    from src.services.llm_client import FallbackLLMClient

    monkeypatch.setattr(llm_client, "LLM_ATTEMPTS", 1)
    primary = GuardedLLMClient(
        OpenAICompatibleClient(
            api_base=BASE,
            api_key="synthetic-key",
            model="failed-primary",
            transport=httpx.MockTransport(lambda request: httpx.Response(503, text="synthetic")),
        ),
        BASE,
        ExternalProcessingPolicy("synthetic-approval", (BASE,)),
    )
    audit, requests = [], []
    async with async_session_factory() as db:
        await resolve_windows(
            db,
            FallbackLLMClient(primary, guarded("fallback-model", requests)),
            (WINDOW,),
            audit=audit,
        )
    calls = audit[0]["provenance"]["llm"]["calls"]
    assert len(calls) == 1 and calls[0]["requested_model"] == "fallback-model"


def test_receipt_collector_restores_outer_context_on_failure():
    import pytest

    from src.services.llm_receipts import capture_receipts, record_receipt

    with capture_receipts() as outer:
        record_receipt({"step": "outer"})
        with pytest.raises(ValueError):
            with capture_receipts() as inner:
                record_receipt({"step": "inner"})
                raise ValueError("synthetic")
        record_receipt({"step": "outer-after"})
    record_receipt({"step": "outside"})
    assert inner == [{"step": "inner"}]
    assert outer == [{"step": "outer"}, {"step": "outer-after"}]
