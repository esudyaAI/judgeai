"""T48 — SSE-поток сообщений дела вместо polling (GET /api/chats/{id}/messages/stream).

Поток шлёт событие `messages` при любом изменении списка, `done` на терминальном статусе
и закрывается; чужой чат и аноним получают те же ответы, что и обычный список.
"""

import asyncio
import json

from src.db.models import Chat, Message
from src.db.session import async_session_factory
from tests.test_auth import account, anonymous, login


async def _seed(user_id: int, assistant_status: str) -> tuple[int, int]:
    async with async_session_factory() as db:
        chat = Chat(owner_id=user_id, title="Поток")
        db.add(chat)
        await db.flush()
        prompt = Message(chat_id=chat.id, role="user", content="вопрос", status="completed")
        db.add(prompt)
        await db.flush()
        answer = Message(
            chat_id=chat.id, role="assistant", status=assistant_status, request_message_id=prompt.id
        )
        db.add(answer)
        await db.commit()
        return chat.id, answer.id


def _events(body: str) -> list[tuple[str, object]]:
    out = []
    for block in body.split("\n\n"):
        event, data = "message", None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event != "message" or data is not None:
            out.append((event, data))
    return out


async def test_stream_requires_login():
    async with anonymous() as client:
        assert (await client.get("/api/chats/1/messages/stream")).status_code == 401


async def test_stream_foreign_chat_is_not_found():
    owner = await account("t48-owner")
    chat_id, _ = await _seed(owner, "completed")
    await account("t48-stranger")
    async with anonymous() as client:
        await login(client, "t48-stranger")
        assert (await client.get(f"/api/chats/{chat_id}/messages/stream")).status_code == 404


async def test_stream_terminal_chat_sends_snapshot_and_done():
    user_id = await account("t48-ready")
    chat_id, _ = await _seed(user_id, "completed")
    async with anonymous() as client:
        await login(client, "t48-ready")
        body = await _read_stream(client, chat_id)
    named = [(event, data) for event, data in _events(body) if event in ("messages", "done")]
    assert [event for event, _ in named] == ["messages", "done"]
    messages = named[0][1]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[-1]["status"] == "completed"


async def test_stream_pushes_update_and_closes_on_terminal():
    user_id = await account("t48-flow")
    chat_id, message_id = await _seed(user_id, "pending")

    async def complete_message() -> None:
        await asyncio.sleep(1.4)
        async with async_session_factory() as db:
            message = await db.get(Message, message_id)
            message.status = "completed"
            message.content = "готово"
            await db.commit()

    async with anonymous() as client:
        await login(client, "t48-flow")
        finisher = asyncio.create_task(complete_message())
        try:
            body = await _read_stream(client, chat_id)
        finally:
            await finisher
    named = [(event, data) for event, data in _events(body) if event in ("messages", "done")]
    kinds = [event for event, _ in named]
    assert kinds[0] == "messages" and kinds.count("done") == 1 and kinds[-1] == "done"
    statuses = [
        [m["status"] for m in data if m["role"] == "assistant"] for event, data in named[:-1]
    ]
    assert statuses[0] == ["pending"] and statuses[-1] == ["completed"]
    assert [m.get("content") for m in named[-2][1] if m["role"] == "assistant"] == ["готово"]


async def _read_stream(client, chat_id: int) -> str:
    async with asyncio.timeout(20):
        async with client.stream("GET", f"/api/chats/{chat_id}/messages/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = ""
            async for chunk in response.aiter_text():
                body += chunk
            return body


async def test_stream_stops_after_chat_deleted():
    from sqlalchemy import delete

    user_id = await account("t48-deleted")
    chat_id, _ = await _seed(user_id, "pending")

    async def remove_chat():
        await asyncio.sleep(0.3)
        async with async_session_factory() as db:
            await db.execute(delete(Chat).where(Chat.id == chat_id))
            await db.commit()

    async with anonymous() as client:
        await login(client, "t48-deleted")
        remover = asyncio.create_task(remove_chat())
        try:
            body = await _read_stream(client, chat_id)
        finally:
            await remover
    assert [name for name, _ in _events(body)] == ["messages", "access_revoked"]


async def test_stream_stops_after_session_revoked():
    from sqlalchemy import delete

    from src.db.auth import UserSession

    user_id = await account("t48-revoked")
    chat_id, _ = await _seed(user_id, "pending")

    async def revoke():
        await asyncio.sleep(0.3)
        async with async_session_factory() as db:
            await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
            await db.commit()

    async with anonymous() as client:
        await login(client, "t48-revoked")
        revoker = asyncio.create_task(revoke())
        try:
            body = await _read_stream(client, chat_id)
        finally:
            await revoker
    assert [name for name, _ in _events(body)] == ["messages", "access_revoked"]


async def test_stream_heartbeat_and_connection_deadline(monkeypatch):
    from src.api import chats

    monkeypatch.setattr(chats, "_STREAM_POLL_SECONDS", 0.2)
    monkeypatch.setattr(chats, "_STREAM_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(chats, "_STREAM_MAX_SECONDS", 0.5)
    user_id = await account("t48-heartbeat")
    chat_id, _ = await _seed(user_id, "pending")
    async with anonymous() as client:
        await login(client, "t48-heartbeat")
        body = await _read_stream(client, chat_id)
    assert body.count("event: messages") == 1
    assert ": ping\n\n" in body
    assert "event: done" not in body


async def test_stream_closes_on_client_disconnect(monkeypatch):
    from starlette.requests import Request

    async def disconnected(self):
        return True

    user_id = await account("t48-disconnected")
    chat_id, _ = await _seed(user_id, "pending")
    async with anonymous() as client:
        await login(client, "t48-disconnected")
        monkeypatch.setattr(Request, "is_disconnected", disconnected)
        body = await _read_stream(client, chat_id)
    assert body.count("event: messages") == 1
    assert "event: done" not in body
