"""Synthetic account lifecycle, owner isolation and literal chat search."""

import base64
from pathlib import Path

from src.db.models import Attachment, Chat, Message
from src.db.session import async_session_factory
from src.services.auth_tokens import token_digest
from tests.test_auth import PASSWORD, account, anonymous, login


async def test_profile_roundtrip_is_private_and_validated():
    await account("alice")
    await account("bob")
    async with anonymous() as alice, anonymous() as bob:
        await login(alice, "alice")
        await login(bob, "bob")
        assert (await alice.get("/api/account/profile")).json()["firstName"] == ""
        profile = {"firstName": " Анна ", "email": "a@example.ru", "org": "Суд"}
        response = await alice.put("/api/account/profile", json=profile)
        assert response.status_code == 200
        assert response.json()["firstName"] == "Анна"
        assert (await alice.get("/api/account/profile")).json()["org"] == "Суд"
        assert (await bob.get("/api/account/profile")).json()["org"] == ""
        for payload in (
            {"avatar": "data:image/svg+xml;base64,PHN2Zz4="},
            {"email": "bad"},
            {"is_admin": True},
            {"firstName": "a" * 101},
        ):
            assert (await alice.put("/api/account/profile", json=payload)).status_code == 422
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic").decode()
        assert (await alice.put("/api/account/profile", json={"avatar": png})).status_code == 200
        csrf = alice.headers.pop("X-CSRF-Token")
        assert (await alice.put("/api/account/profile", json={})).status_code == 403
        alice.headers["X-CSRF-Token"] = csrf


async def test_password_change_revokes_other_sessions_and_preserves_current():
    await account("alice")
    async with anonymous() as current, anonymous() as other:
        await login(current, "alice")
        await login(other, "alice")
        wrong = {"current_password": "wrong-secret", "new_password": "new-synthetic-password"}
        response = await current.post("/api/account/password", json=wrong)
        assert response.status_code == 400
        assert "wrong-secret" not in response.text
        assert (
            await current.post("/api/account/password", json={**wrong, "new_password": "short"})
        ).status_code == 422
        response = await current.post(
            "/api/account/password", json={**wrong, "current_password": PASSWORD}
        )
        assert response.status_code == 200
        assert (await current.get("/api/auth/me")).status_code == 200
        assert (await other.get("/api/auth/me")).status_code == 401
        async with anonymous() as fresh:
            assert (
                await fresh.post(
                    "/api/auth/login",
                    json={"username": "alice", "password": PASSWORD},
                    headers={"X-Requested-With": "JudgeAI"},
                )
            ).status_code == 401
            assert (
                await fresh.post(
                    "/api/auth/login",
                    json={"username": "alice", "password": "new-synthetic-password"},
                    headers={"X-Requested-With": "JudgeAI"},
                )
            ).status_code == 200


async def test_session_references_cannot_revoke_another_users_session():
    await account("alice")
    await account("bob")
    async with anonymous() as alice, anonymous() as other, anonymous() as bob:
        await login(alice, "alice")
        await login(other, "alice")
        await login(bob, "bob")
        sessions = (await alice.get("/api/account/sessions")).json()
        assert len(sessions) == 2
        token = alice.cookies.get("judgeai_session")
        assert token not in str(sessions)
        assert token_digest(token) not in str(sessions)
        target = next(s for s in sessions if not s["current"])
        assert (await bob.delete(f"/api/account/sessions/{target['id']}")).status_code == 404
        assert (await alice.delete(f"/api/account/sessions/{target['id']}")).status_code == 200
        assert (await other.get("/api/auth/me")).status_code == 401
        own = next(s for s in sessions if s["current"])
        assert (await alice.delete(f"/api/account/sessions/{own['id']}")).status_code == 404
        assert (await bob.get("/api/auth/me")).status_code == 200


async def seed_chat(owner_id, title, text="synthetic-text", filename="document.txt", path=""):
    async with async_session_factory() as db:
        chat = Chat(owner_id=owner_id, title=title)
        db.add(chat)
        await db.flush()
        message = Message(chat_id=chat.id, role="user", content=text, status="completed")
        db.add(message)
        await db.flush()
        db.add(
            Attachment(
                message_id=message.id,
                filename=filename,
                stored_path=path,
                extracted_text="synthetic-extracted",
            )
        )
        await db.commit()
        return chat.id


async def test_search_owner_title_messages_files_and_literal_wildcards():
    alice_id = await account("alice")
    bob_id = await account("bob")
    title_id = await seed_chat(alice_id, "Особое ДЕЛО")
    body_id = await seed_chat(alice_id, "Other", "редкое сообщение")
    file_id = await seed_chat(alice_id, "Files", filename="Протокол_100%.txt")
    await seed_chat(bob_id, "Особое ДЕЛО", "редкое сообщение", "Протокол_100%.txt")
    async with anonymous() as alice:
        await login(alice, "alice")
        for query, expected in (
            ("дело", title_id),
            ("Сообщение", body_id),
            ("протокол", file_id),
            ("100%", file_id),
            ("_", file_id),
        ):
            response = await alice.get("/api/chats", params={"q": query})
            assert response.status_code == 200
            assert [c["id"] for c in response.json()] == [expected]
        assert (await alice.get("/api/chats", params={"q": "nothing"})).json() == []
        assert len((await alice.get("/api/chats", params={"q": "   "})).json()) == 3
        assert (await alice.get("/api/chats", params={"q": "x" * 201})).status_code == 422


async def test_export_and_delete_only_own_data(tmp_path):
    from src.config import settings

    alice_id = await account("alice")
    bob_id = await account("bob")
    path = Path(settings.UPLOAD_DIR) / "synthetic.txt"
    path.write_text("synthetic-upload")
    outside = tmp_path / "outside-root.txt"
    outside.write_text("do-not-delete")
    await seed_chat(alice_id, "Alice private", path=str(path))
    await seed_chat(alice_id, "Outside", path=str(outside))
    bob_chat = await seed_chat(bob_id, "Bob private")
    async with anonymous() as alice, anonymous() as bob:
        await login(alice, "alice")
        await login(bob, "bob")
        exported = await alice.get("/api/account/export")
        assert exported.status_code == 200
        assert exported.headers["cache-control"] == "no-store"
        assert "Bob private" not in exported.text
        assert "stored_path" not in exported.text
        assert "password_hash" not in exported.text
        assert "synthetic-extracted" in exported.text
        assert len(exported.json()["chats"]) == 2
        payload = {"password": PASSWORD, "confirmation": "УДАЛИТЬ"}
        assert (
            await alice.post("/api/account/delete-cases", json={**payload, "confirmation": ""})
        ).status_code == 400
        assert (
            await alice.post("/api/account/delete-cases", json={**payload, "password": "wrong"})
        ).status_code == 400
        response = await alice.post("/api/account/delete-cases", json=payload)
        assert response.status_code == 200
        assert response.json() == {"deleted": 2, "files_pending": 1}
        assert not path.exists()
        assert outside.exists()
        assert (await alice.get("/api/chats")).json() == []
        assert [c["id"] for c in (await bob.get("/api/chats")).json()] == [bob_chat]
        assert (await alice.get("/api/auth/me")).status_code == 200


async def test_busy_analysis_blocks_delete_and_requires_csrf():
    owner = await account("alice")
    chat = await seed_chat(owner, "Busy")
    async with async_session_factory() as db:
        db.add(Message(chat_id=chat, role="assistant", status="running"))
        await db.commit()
    async with anonymous() as alice:
        await login(alice, "alice")
        payload = {"password": PASSWORD, "confirmation": "УДАЛИТЬ"}
        assert (await alice.post("/api/account/delete-cases", json=payload)).status_code == 409
        assert len((await alice.get("/api/chats")).json()) == 1
        alice.headers.pop("X-CSRF-Token")
        assert (await alice.post("/api/account/delete-cases", json=payload)).status_code == 403


async def test_account_actions_require_sign_in():
    async with anonymous() as client:
        for route in ("profile", "sessions", "export"):
            assert (await client.get(f"/api/account/{route}")).status_code == 401


async def test_shared_upload_is_not_removed_with_one_owners_cases():
    from src.config import settings

    alice_id = await account("alice")
    bob_id = await account("bob")
    shared = Path(settings.UPLOAD_DIR) / "shared-synthetic.txt"
    shared.write_text("synthetic-shared")
    await seed_chat(alice_id, "Alice", path=str(shared))
    await seed_chat(bob_id, "Bob", path=str(shared))
    async with anonymous() as alice:
        await login(alice, "alice")
        payload = {"password": PASSWORD, "confirmation": "УДАЛИТЬ"}
        response = await alice.post("/api/account/delete-cases", json=payload)
        assert response.json()["deleted"] == 1
        assert shared.exists()
        assert (await alice.post("/api/account/delete-cases", json=payload)).json()["deleted"] == 0


async def test_password_attempts_are_limited_and_validation_never_echoes_secrets():
    await account("alice")
    async with anonymous() as alice:
        await login(alice, "alice")
        response = await alice.post(
            "/api/account/password",
            json={
                "current_password": "synthetic-private-value",
                "new_password": "secret42",
            },
        )
        assert response.status_code == 422
        assert "synthetic-private-value" not in response.text
        assert "secret42" not in response.text
        for _ in range(10):
            response = await alice.post(
                "/api/account/password",
                json={
                    "current_password": "wrong",
                    "new_password": "synthetic-new-password",
                },
            )
            assert response.status_code == 400
        assert (
            await alice.post(
                "/api/account/password",
                json={
                    "current_password": "wrong",
                    "new_password": "synthetic-new-password",
                },
            )
        ).status_code == 429
