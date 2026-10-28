"""Open self-registration: anyone may create an ordinary (non-admin) account."""

import httpx
from sqlalchemy import select

from src.db.auth import User
from src.db.session import async_session_factory
from src.main import app
from src.services.auth import REGISTRATIONS_PER_HOST

PASSWORD = "synthetic-test-password-42"
HEADERS = {"X-Requested-With": "JudgeAI"}


def anonymous():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def register(client, username="ivanov", password=PASSWORD, headers=HEADERS):
    return await client.post(
        "/api/auth/register", json={"username": username, "password": password}, headers=headers
    )


async def test_registration_creates_an_ordinary_account_and_signs_in():
    async with anonymous() as client:
        r = await register(client, username="  Ivanov.Judge ")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["username"] == "ivanov.judge" and body["is_admin"] is False
        assert body["csrf_token"] and PASSWORD not in r.text
        assert "httponly" in r.headers["set-cookie"].lower()
        client.headers["X-CSRF-Token"] = body["csrf_token"]
        assert (await client.get("/api/auth/me")).json()["username"] == "ivanov.judge"
        assert (await client.post("/api/chats", json={"title": None})).status_code in (200, 201)
    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.username == "ivanov.judge"))
        assert user.is_active and not user.is_admin
        assert user.password_hash and PASSWORD not in user.password_hash


async def test_registered_user_can_sign_in_again():
    async with anonymous() as client:
        await register(client)
    async with anonymous() as client:
        r = await client.post(
            "/api/auth/login", json={"username": "ivanov", "password": PASSWORD}, headers=HEADERS
        )
        assert r.status_code == 200


async def test_taken_username_is_rejected_in_russian():
    async with anonymous() as client:
        assert (await register(client)).status_code == 201
    async with anonymous() as client:
        r = await register(client, username="IVANOV")
        assert r.status_code == 409 and "занято" in r.json()["detail"]


async def test_short_password_and_bad_username_are_rejected():
    async with anonymous() as client:
        short = await register(client, password="short")
        assert short.status_code == 422 and "12" in short.json()["detail"]
        assert "short" not in short.text
        for bad in ("ab", "иванов", "a b c", "-start"):
            r = await register(client, username=bad)
            assert r.status_code == 422, bad
    async with async_session_factory() as db:
        assert (await db.scalars(select(User))).all() == []


async def test_registration_requires_the_request_header():
    async with anonymous() as client:
        assert (await register(client, headers={})).status_code == 403


async def test_registrations_from_one_host_are_limited():
    async with anonymous() as client:
        for i in range(REGISTRATIONS_PER_HOST):
            assert (await register(client, username=f"user{i:03d}")).status_code == 201
        r = await register(client, username="one-too-many")
        assert r.status_code == 429 and "Слишком много" in r.json()["detail"]
