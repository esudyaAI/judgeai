"""Sidebar dot: a failed analysis stays visible until a real re-analysis completes (T47).

A completed text-only answer without case content («Вопрос не содержит сведений…»)
must not repaint the failed case as ready; a re-analysis with documents/defendants
must. Purely textual chats keep the ready dot.
"""

from src.db.models import Chat, Message
from src.db.session import async_session_factory
from tests.test_auth import account, anonymous, login

CASE_CONTENT = {"defendants": [{"name": "Иванов"}], "stats": {"documents": 1}}
DEGENERATE = {"defendants": [], "stats": {"documents": 0}}


async def _seed_chat(user_id: int, messages: list[dict]) -> int:
    async with async_session_factory() as db:
        chat = Chat(owner_id=user_id, title="Статус точки")
        db.add(chat)
        await db.flush()
        for spec in messages:
            prompt = Message(chat_id=chat.id, role="user", content="вопрос", status="completed")
            db.add(prompt)
            await db.flush()
            db.add(
                Message(
                    chat_id=chat.id,
                    role="assistant",
                    status=spec["status"],
                    analysis=spec.get("analysis"),
                    error=spec.get("error"),
                    request_message_id=prompt.id,
                )
            )
        await db.commit()
        return chat.id


async def test_degenerate_followup_does_not_hide_failed_analysis():
    user_id = await account("t47-failed")
    chat_id = await _seed_chat(
        user_id,
        [
            {"status": "failed", "error": "Языковая модель не подключена"},
            {"status": "completed", "analysis": DEGENERATE},
        ],
    )
    async with anonymous() as client:
        await login(client, "t47-failed")
        assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "failed"
        assert (await client.get("/api/chats")).json()[0]["status"] == "failed"


async def test_reanalysis_with_case_content_recovers_to_ready():
    user_id = await account("t47-recovered")
    chat_id = await _seed_chat(
        user_id,
        [
            {"status": "failed", "error": "сбой"},
            {"status": "completed", "analysis": CASE_CONTENT},
        ],
    )
    async with anonymous() as client:
        await login(client, "t47-recovered")
        assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "ready"


async def test_pure_text_chat_stays_ready():
    user_id = await account("t47-text")
    chat_id = await _seed_chat(user_id, [{"status": "completed", "analysis": DEGENERATE}])
    async with anonymous() as client:
        await login(client, "t47-text")
        assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "ready"


async def test_running_analysis_is_busy_and_ready_case_survives_text_followup():
    user_id = await account("t47-running")
    chat_id = await _seed_chat(
        user_id,
        [
            {"status": "completed", "analysis": CASE_CONTENT},
            {"status": "completed", "analysis": DEGENERATE},
        ],
    )
    async with anonymous() as client:
        await login(client, "t47-running")
        assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "ready"


async def test_chat_without_assistant_messages_is_draft():
    user_id = await account("t47-draft")
    async with async_session_factory() as db:
        chat = Chat(owner_id=user_id, title="Только пользовательские сообщения")
        db.add(chat)
        await db.flush()
        db.add(Message(chat_id=chat.id, role="user", content="проверь", status="completed"))
        await db.commit()
        chat_id = chat.id
    async with anonymous() as client:
        await login(client, "t47-draft")
        assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "draft"
