"""Two-user adversarial checks; synthetic fixtures only."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from src.db.auth import User, UserSession
from src.db.models import Chat
from src.db.session import async_session_factory
from src.main import app
from src.services.auth import UserContext, hash_password
from src.services.auth_tokens import token_digest

PASSWORD = "synthetic-test-password-42"


async def account(username, *, active=True):
    async with async_session_factory() as db:
        user = User(
            username=username, password_hash=await hash_password(PASSWORD), is_active=active
        )
        db.add(user)
        await db.commit()
        return user.id


def anonymous():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def login(client, username):
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": PASSWORD},
        headers={"X-Requested-With": "JudgeAI"},
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


async def test_login_logout_and_revoked_session():
    await account("alice")
    async with anonymous() as client:
        assert (await client.get("/api/chats")).status_code == 401
        response = await login(client, "alice")
        assert "password" not in str(response.json())
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        token = client.cookies.get("judgeai_session")
        async with async_session_factory() as db:
            assert await db.get(UserSession, token_digest(token)) is not None
            assert await db.get(UserSession, token) is None
        assert (await client.get("/api/auth/me")).json()["username"] == "alice"
        assert (await client.post("/api/auth/logout")).status_code == 200
        client.cookies.set("judgeai_session", token)
        assert (await client.get("/api/chats")).status_code == 401


async def test_login_csrf_invalid_password_disabled_and_throttle():
    await account("disabled", active=False)
    async with anonymous() as client:
        payload = {"username": "disabled", "password": PASSWORD}
        assert (await client.post("/api/auth/login", json=payload)).status_code == 403
        for _ in range(10):
            username = "disabled"
            response = await client.post(
                "/api/auth/login",
                json={**payload, "username": username},
                headers={"X-Requested-With": "JudgeAI"},
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Неверное имя пользователя или пароль"
        assert (
            await client.post(
                "/api/auth/login", json=payload, headers={"X-Requested-With": "JudgeAI"}
            )
        ).status_code == 429


async def test_expired_disabled_and_missing_csrf_sessions():
    user_id = await account("alice")
    async with anonymous() as client:
        await login(client, "alice")
        csrf = client.headers.pop("X-CSRF-Token")
        assert (await client.post("/api/chats", json={})).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (await client.post("/api/chats", json={})).status_code == 201
        async with async_session_factory() as db:
            user = await db.get(User, user_id)
            user.is_active = False
            await db.commit()
        assert (await client.get("/api/auth/me")).status_code == 401
        async with async_session_factory() as db:
            user = await db.get(User, user_id)
            user.is_active = True
            session = await db.scalar(select(UserSession).where(UserSession.user_id == user_id))
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_two_users_cannot_read_post_or_poll_foreign_case_or_result(monkeypatch):
    await account("alice")
    await account("bob")
    async with anonymous() as alice, anonymous() as bob:
        await login(alice, "alice")
        await login(bob, "bob")
        case = (await alice.post("/api/chats", json={"title": "Private Alice"})).json()["id"]
        result = await alice.post(
            f"/api/chats/{case}/messages",
            data={"content": "Synthetic case", "use_knowledge_base": "false"},
        )
        assert result.status_code == 202
        message = result.json()["assistant_message"]["id"]
        assert (await bob.get("/api/chats")).json() == []
        for suffix in ("", "/messages", f"/messages/{message}"):
            response = await bob.get(f"/api/chats/{case}{suffix}")
            assert response.status_code == 404
            assert "Private Alice" not in response.text
        assert (
            await bob.post(f"/api/chats/{case}/messages", data={"content": "forbidden"})
        ).status_code == 404
        # The shared practice base is open to every signed-in user (owner decision 28.10.2026);
        # private case documents stay out of it (tests/test_practice_base_access.py).
        assert (await bob.get("/api/knowledge/verdicts")).status_code == 200
        assert (
            await alice.post(
                f"/api/chats/{case}/messages",
                data={"content": "with practice", "use_knowledge_base": "true"},
            )
        ).status_code == 202
        assert (await alice.get(f"/api/chats/{case}/messages/{message}")).status_code == 200


async def test_legacy_unassigned_case_is_not_visible_to_new_account():
    await account("alice")
    async with async_session_factory() as db:
        db.add(Chat(title="Unassigned legacy case"))
        await db.commit()
    async with anonymous() as client:
        await login(client, "alice")
        assert (await client.get("/api/chats")).json() == []


async def test_background_rejects_cross_owner_and_mismatched_messages(monkeypatch):
    from src.db.models import Message
    from src.services.analysis_runner import run_analysis

    alice_id = await account("alice")
    bob_id = await account("bob")
    async with async_session_factory() as db:
        first, second = Chat(owner_id=alice_id), Chat(owner_id=bob_id)
        db.add_all([first, second])
        await db.flush()
        request = Message(chat_id=first.id, role="user", content="Private Alice")
        db.add(request)
        await db.flush()
        result = Message(
            chat_id=first.id, role="assistant", status="pending", request_message_id=request.id
        )
        foreign_result = Message(chat_id=second.id, role="assistant", status="pending")
        db.add_all([request, result, foreign_result])
        await db.commit()

    def forbidden():
        pytest.fail("Unauthorized job must not invoke LLM")

    monkeypatch.setattr("src.services.analysis_runner.get_llm_client", forbidden)
    for target, user in [
        (result.id, UserContext(bob_id, "bob")),
        (foreign_result.id, UserContext(alice_id, "alice")),
    ]:
        await run_analysis(request.id, target, user=user, use_knowledge_base=False)
    async with async_session_factory() as db:
        assert (await db.get(Message, result.id)).status == "pending"
        assert (await db.get(Message, foreign_result.id)).status == "pending"


async def test_successful_logins_do_not_exhaust_shared_proxy_budget():
    await account("alice")
    async with anonymous() as client:
        for _ in range(12):
            await login(client, "alice")
        await account("bob")
        await login(client, "bob")


async def test_failing_account_does_not_consume_another_accounts_limit():
    await account("alice")
    await account("bob")
    async with anonymous() as client:
        for _ in range(10):
            response = await client.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong"},
                headers={"X-Requested-With": "JudgeAI"},
            )
            assert response.status_code == 401
        await login(client, "bob")


async def test_same_chat_mismatched_or_completed_reply_is_not_overwritten(monkeypatch):
    from src.db.models import Message
    from src.services.analysis_runner import run_analysis

    owner = await account("alice")
    async with async_session_factory() as db:
        chat = Chat(owner_id=owner)
        db.add(chat)
        await db.flush()
        first = Message(chat_id=chat.id, role="user", content="Request A")
        second = Message(chat_id=chat.id, role="user", content="Request B")
        db.add_all([first, second])
        await db.flush()
        reply = Message(
            chat_id=chat.id,
            role="assistant",
            status="pending",
            request_message_id=second.id,
            content="Original result",
        )
        db.add(reply)
        await db.commit()

    def forbidden():
        pytest.fail("Mismatched or completed reply must not invoke LLM")

    monkeypatch.setattr("src.services.analysis_runner.get_llm_client", forbidden)
    await run_analysis(
        first.id, reply.id, user=UserContext(owner, "alice"), use_knowledge_base=False
    )
    async with async_session_factory() as db:
        stored = await db.get(Message, reply.id)
        assert stored.content == "Original result" and stored.status == "pending"
        stored.status = "completed"
        await db.commit()
    await run_analysis(
        second.id, reply.id, user=UserContext(owner, "alice"), use_knowledge_base=False
    )
    async with async_session_factory() as db:
        assert (await db.get(Message, reply.id)).content == "Original result"


async def test_invalid_login_body_never_echoes_password():
    async with anonymous() as client:
        response = await client.post(
            "/api/auth/login", json={"password": PASSWORD}, headers={"X-Requested-With": "JudgeAI"}
        )
        assert response.status_code == 422
        assert PASSWORD not in response.text
        assert "input" not in response.text
