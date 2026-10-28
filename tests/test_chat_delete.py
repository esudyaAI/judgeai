"""Deleting one case must preserve all other users, cases, practice and shared files."""

from pathlib import Path

import pytest
from sqlalchemy import select

from src.config import settings
from src.db.models import Attachment, Chat, KnowledgeVerdict, Message
from src.db.session import async_session_factory
from tests.test_auth import account, anonymous, login


async def test_delete_one_chat_cascades_and_preserves_other_data():
    alice_id = await account("alice")
    bob_id = await account("bob")
    root = Path(settings.UPLOAD_DIR)
    root.mkdir(exist_ok=True)
    own_file, shared_file = root / "delete-one.txt", root / "shared-one.txt"
    own_file.write_text("synthetic")
    shared_file.write_text("synthetic shared")
    async with async_session_factory() as db:
        target = Chat(owner_id=alice_id, title="delete me")
        keep = Chat(owner_id=alice_id, title="keep mine")
        foreign = Chat(owner_id=bob_id, title="keep theirs")
        db.add_all([target, keep, foreign, KnowledgeVerdict(raw_text="shared practice")])
        await db.flush()
        removed = Message(chat_id=target.id, role="user", status="completed")
        preserved = Message(chat_id=foreign.id, role="user", status="completed")
        db.add_all([removed, preserved])
        await db.flush()
        for message_id, path in [
            (removed.id, own_file),
            (removed.id, shared_file),
            (preserved.id, shared_file),
        ]:
            db.add(Attachment(message_id=message_id, filename=path.name, stored_path=str(path)))
        await db.commit()
        target_id, keep_id, foreign_id = target.id, keep.id, foreign.id
    async with anonymous() as alice, anonymous() as bob:
        await login(alice, "alice")
        await login(bob, "bob")
        assert (await bob.delete(f"/api/chats/{target_id}")).status_code == 404
        csrf = alice.headers.pop("X-CSRF-Token")
        assert (await alice.delete(f"/api/chats/{target_id}")).status_code == 403
        alice.headers["X-CSRF-Token"] = csrf
        response = await alice.delete(f"/api/chats/{target_id}")
        assert response.status_code == 200
        assert response.json() == {"deleted": 1, "files_pending": 0}
        assert (await alice.get(f"/api/chats/{target_id}")).status_code == 404
        assert (await alice.delete(f"/api/chats/{target_id}")).status_code == 404
        assert (await alice.get(f"/api/chats/{keep_id}")).status_code == 200
        assert (await bob.get(f"/api/chats/{foreign_id}")).status_code == 200
    assert not own_file.exists()
    assert shared_file.exists()
    async with async_session_factory() as db:
        assert await db.scalar(select(Message.id).where(Message.chat_id == target_id)) is None
        assert len((await db.scalars(select(Attachment))).all()) == 1
        assert await db.scalar(select(KnowledgeVerdict.id)) is not None


@pytest.mark.parametrize("status", ["pending", "running"])
async def test_delete_busy_chat_is_rejected(status):
    user_id = await account("alice")
    async with async_session_factory() as db:
        chat = Chat(owner_id=user_id)
        db.add(chat)
        await db.flush()
        db.add(Message(chat_id=chat.id, role="assistant", status=status))
        await db.commit()
        chat_id = chat.id
    async with anonymous() as client:
        await login(client, "alice")
        assert (await client.delete(f"/api/chats/{chat_id}")).status_code == 409
        assert (await client.get(f"/api/chats/{chat_id}")).status_code == 200


async def test_delete_requires_authentication():
    async with anonymous() as client:
        assert (await client.delete("/api/chats/999999")).status_code == 401
