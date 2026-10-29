"""Saved analyses carry the engine version; stale ones can be recalculated (T43).

A completed analysis is stamped with ANALYSIS_VERSION, marked ``stale`` when the
stored version differs (including pre-T43 results without the field), and
``POST .../recalculate`` re-runs the stored exchange in place.
"""

from src.db.models import Message
from src.db.session import async_session_factory
from src.domain.analysis_version import ANALYSIS_VERSION


def _txt(body="Подсудимый похитил ноутбук"):
    return ("files", ("Приговор.txt", body.encode("utf-8"), "text/plain"))


async def _analysed_chat(client) -> tuple[int, int]:
    r = await client.post("/api/chats", json={"title": "Пересчёт"})
    chat_id = r.json()["id"]
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Подготовь проект приговора"},
        files=[_txt("Подсудимый похитил ноутбук. Отягчающих обстоятельств не установлено.")],
    )
    return chat_id, r.json()["assistant_message"]["id"]


async def test_fresh_analysis_is_stamped_and_not_stale(client):
    chat_id, msg_id = await _analysed_chat(client)
    r = await client.get(f"/api/chats/{chat_id}/messages")
    msg = next(m for m in r.json() if m["id"] == msg_id)
    assert msg["status"] == "completed"
    assert msg["result"]["engine_version"] == ANALYSIS_VERSION
    assert msg["stale"] is False


async def test_old_analysis_without_engine_version_is_stale(client):
    chat_id, msg_id = await _analysed_chat(client)
    async with async_session_factory() as db:
        stored = await db.get(Message, msg_id)
        analysis = dict(stored.analysis)
        analysis.pop("engine_version", None)
        stored.analysis = analysis
        await db.commit()
    r = await client.get(f"/api/chats/{chat_id}/messages")
    msg = next(m for m in r.json() if m["id"] == msg_id)
    assert msg["result"] is not None
    assert msg["stale"] is True


async def test_recalculate_reruns_the_stored_exchange(client):
    chat_id, msg_id = await _analysed_chat(client)
    r = await client.post(f"/api/chats/{chat_id}/messages/{msg_id}/recalculate")
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert r.json()["stale"] is None or r.json()["stale"] is False
    r = await client.get(f"/api/chats/{chat_id}/messages")
    msg = next(m for m in r.json() if m["id"] == msg_id)
    assert msg["status"] == "completed", msg["error"]
    assert msg["result"] is not None
    assert msg["result"]["engine_version"] == ANALYSIS_VERSION
    assert msg["stale"] is False
    # The exchange is one message pair, not a growing thread.
    assert len(r.json()) == 2


async def test_recalculate_rejects_foreign_and_wrong_targets(client):
    chat_id, msg_id = await _analysed_chat(client)
    r = await client.get(f"/api/chats/{chat_id}/messages")
    user_msg = next(m for m in r.json() if m["role"] == "user")
    # a user message is not recalculated
    assert (
        await client.post(f"/api/chats/{chat_id}/messages/{user_msg['id']}/recalculate")
    ).status_code == 404
    # a message of another chat
    assert (
        await client.post(f"/api/chats/{chat_id + 999}/messages/{msg_id}/recalculate")
    ).status_code == 404


async def test_recalculate_is_rejected_while_analysis_is_running(client, monkeypatch):
    chat_id, _ = await _analysed_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/messages", data={"content": "ещё вопрос"}, files=[_txt()]
    )
    msg_id = r.json()["assistant_message"]["id"]
    # Mark it running directly: the endpoint must refuse concurrent recalculations.
    async with async_session_factory() as db:
        stored = await db.get(Message, msg_id)
        stored.status = "running"
        await db.commit()
    try:
        response = await client.post(f"/api/chats/{chat_id}/messages/{msg_id}/recalculate")
        assert response.status_code == 409
    finally:
        async with async_session_factory() as db:
            stored = await db.get(Message, msg_id)
            stored.status = "failed"
            stored.error = "тест"
            await db.commit()


async def test_recalculate_requires_csrf(client):
    chat_id, msg_id = await _analysed_chat(client)
    token = client.headers.pop("X-CSRF-Token")
    try:
        response = await client.post(f"/api/chats/{chat_id}/messages/{msg_id}/recalculate")
        assert response.status_code == 403
    finally:
        client.headers["X-CSRF-Token"] = token
