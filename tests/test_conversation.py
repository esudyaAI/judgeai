from sqlalchemy import select

from src.db.models import Chat, Message
from src.db.session import async_session_factory
from src.infrastructure.conversation import load_conversation
from tests.test_auth import account


async def test_follow_up_uses_previous_documents_and_keeps_all_messages(client, monkeypatch):
    from src.services.case_analyzer import extract_facts as original

    calls = []

    async def record(llm, question, texts, items):
        calls.append((question, texts))
        return await original(llm, question, texts, items)

    monkeypatch.setattr("src.services.analysis_runner.extract_facts", record)
    chat = (await client.post("/api/chats", json={"title": "history"})).json()["id"]
    first = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "First question"},
        files={"files": ("case.txt", b"Synthetic evidence marker")},
    )
    assert first.status_code == 202
    second = await client.post(
        f"/api/chats/{chat}/messages", data={"content": "Follow-up question"}
    )
    assert second.status_code == 202
    messages = (await client.get(f"/api/chats/{chat}/messages")).json()
    assert len(messages) == 4
    assert messages[-1]["status"] == "completed"
    assert messages[-1]["result"]["stats"]["documents"] == 1
    assert "First question" in calls[-1][0]
    assert calls[-1][0].endswith("Follow-up question")
    assert any("Synthetic evidence marker" in text for text in calls[-1][1])
    async with async_session_factory() as db:
        owner = await db.scalar(select(Chat.owner_id).where(Chat.id == chat))
        stranger = await account("stranger")
        isolated = await load_conversation(db, stranger, chat, messages[-1]["id"] + 1, "test")
        assert not isolated.documents
        assert isolated.question == "test"
        assert owner != stranger


async def test_busy_chat_rejects_second_message_before_file_writes(client):
    chat = (await client.post("/api/chats", json={"title": "busy"})).json()["id"]
    async with async_session_factory() as db:
        db.add(Message(chat_id=chat, role="assistant", status="running"))
        await db.commit()
    response = await client.post(f"/api/chats/{chat}/messages", data={"content": "duplicate"})
    assert response.status_code == 409
    assert len((await client.get(f"/api/chats/{chat}/messages")).json()) == 1


async def test_old_attachment_survives_long_chat_and_answer_details_are_context(client):
    from src.db.models import Attachment

    chat = (await client.post("/api/chats", json={"title": "long history"})).json()["id"]
    async with async_session_factory() as db:
        first = Message(chat_id=chat, role="user", content="First", status="completed")
        db.add(first)
        await db.flush()
        db.add(
            Attachment(
                message_id=first.id,
                filename="old.txt",
                stored_path="unused",
                extracted_text="Old readable evidence",
                page_count=2,
                extraction_status="ok",
            )
        )
        for index in range(45):
            db.add(
                Message(
                    chat_id=chat,
                    role="user" if index % 2 else "assistant",
                    content=f"Turn {index}",
                    status="completed",
                )
            )
        await db.flush()
        reply = Message(
            chat_id=chat,
            role="assistant",
            content="Only fabula",
            status="completed",
            analysis={
                "variants": [{"title": "Second option marker"}],
                "scale": {"recommended_months": 42},
                "warnings": ["Synthetic warning marker"],
            },
        )
        db.add(reply)
        await db.commit()
        owner = await db.scalar(select(Chat.owner_id).where(Chat.id == chat))
        context = await load_conversation(
            db, owner, chat, reply.id + 1, "Explain the second option"
        )
        assert any(d.text == "Old readable evidence" for d in context.documents)
        assert "Second option marker" in context.question
        assert "42" in context.question
        assert "Synthetic warning marker" in context.question
