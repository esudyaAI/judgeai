"""Upgrade/downgrade only the new profile table, preserving existing private records."""

import asyncio

from alembic import command
from sqlalchemy import text

from src.db.session import engine
from tests.conftest import alembic_config


def test_profile_migration_preserves_accounts_and_chats():
    async def seed():
        async with engine.begin() as db:
            user_id = await db.scalar(
                text("INSERT INTO users (username) VALUES ('migration-user') RETURNING id")
            )
            await db.execute(
                text("INSERT INTO chats (owner_id, title) VALUES (:id, 'private-migration-case')"),
                {"id": user_id},
            )

    async def check():
        async with engine.begin() as db:
            assert (
                await db.scalar(text("SELECT count(*) FROM users WHERE username='migration-user'"))
                == 1
            )
            assert (
                await db.scalar(
                    text("SELECT count(*) FROM chats WHERE title='private-migration-case'")
                )
                == 1
            )

    asyncio.run(seed())
    command.downgrade(alembic_config(), "0008_precedent_embeddings")
    try:
        asyncio.run(check())
    finally:
        command.upgrade(alembic_config(), "head")
    asyncio.run(check())
