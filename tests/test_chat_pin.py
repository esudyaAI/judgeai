from tests.test_auth import account, anonymous, login


async def test_pin_is_owner_scoped_persisted_and_sorted_first():
    await account("alice")
    await account("bob")
    async with anonymous() as alice, anonymous() as bob:
        await login(alice, "alice")
        await login(bob, "bob")
        first = (await alice.post("/api/chats", json={"title": "First"})).json()["id"]
        second = (await alice.post("/api/chats", json={"title": "Second"})).json()["id"]
        url = f"/api/chats/{first}/pin"
        assert (await bob.patch(url, json={"pinned": True})).status_code == 404
        csrf = alice.headers.pop("X-CSRF-Token")
        assert (await alice.patch(url, json={"pinned": True})).status_code == 403
        alice.headers["X-CSRF-Token"] = csrf
        result = await alice.patch(url, json={"pinned": True})
        assert result.status_code == 200
        assert result.json()["is_pinned"] is True
        chats = (await alice.get("/api/chats")).json()
        assert [c["id"] for c in chats] == [first, second]
        assert (await alice.get(f"/api/chats/{first}")).json()["is_pinned"] is True
        assert (await alice.patch(url, json={"pinned": False})).json()["is_pinned"] is False
        assert (await alice.get("/api/chats")).json()[0]["id"] == second
        assert (
            await alice.patch("/api/chats/999999/pin", json={"pinned": True})
        ).status_code == 404
        assert (await bob.get("/api/chats")).json() == []


def test_pin_migration_backfill_and_rollback_preserve_chat():
    import asyncio

    from alembic import command
    from sqlalchemy import text

    from src.db.session import async_session_factory
    from tests.conftest import alembic_config

    async def execute(sql):
        async with async_session_factory() as db:
            result = await db.execute(text(sql))
            row = result.first() if result.returns_rows else None
            await db.commit()
            return row

    cfg = alembic_config()
    command.downgrade(cfg, "0011_embedding_any_dimension")
    try:
        row = asyncio.run(
            execute("INSERT INTO chats (title) VALUES ('Synthetic pin migration') RETURNING id")
        )
        chat = int(row[0])
        command.upgrade(cfg, "head")
        assert asyncio.run(execute(f"SELECT is_pinned FROM chats WHERE id={chat}"))[0] is False
        asyncio.run(execute(f"UPDATE chats SET is_pinned=true WHERE id={chat}"))
        command.downgrade(cfg, "0011_embedding_any_dimension")
        assert (
            asyncio.run(execute(f"SELECT title FROM chats WHERE id={chat}"))[0]
            == "Synthetic pin migration"
        )
    finally:
        command.upgrade(cfg, "head")
