from sqlalchemy import delete, func, select

from src.db.llm_window_extractions import PrivateLlmWindowExtraction
from src.db.models import Chat, LlmWindowExtraction
from src.db.session import async_session_factory
from src.services.punishment_window_resolver import resolve_windows
from tests.test_auth import account
from tests.test_punishment_window_resolver import WINDOW, CountingLlm


async def test_private_cache_is_reused_only_inside_its_own_chat_and_deleted_with_it():
    owners = [await account("cache-owner-a"), await account("cache-owner-b")]
    llm = CountingLlm({"kind": "imprisonment", "years": 2, "quote": "лишения свободы"})
    async with async_session_factory() as db:
        chats = [Chat(owner_id=owner, title="synthetic") for owner in owners]
        db.add_all(chats)
        await db.commit()
        # Old shared cache remains intact but is not read for private cases.
        await resolve_windows(db, llm, (WINDOW,))
        assert llm.calls == 1
        for _ in range(2):
            await resolve_windows(db, llm, (WINDOW,), chat_id=chats[0].id)
        assert llm.calls == 2
        await resolve_windows(db, llm, (WINDOW,), chat_id=chats[1].id)
        assert llm.calls == 3
        assert await db.scalar(select(func.count()).select_from(PrivateLlmWindowExtraction)) == 2
        assert await db.scalar(select(func.count()).select_from(LlmWindowExtraction)) == 1
        await db.execute(delete(Chat).where(Chat.id == chats[0].id))
        await db.commit()
        remaining = (await db.scalars(select(PrivateLlmWindowExtraction))).all()
        assert len(remaining) == 1 and remaining[0].chat_id == chats[1].id
        assert await db.scalar(select(func.count()).select_from(LlmWindowExtraction)) == 1


def test_populated_private_cache_refuses_destructive_downgrade():
    import asyncio

    import pytest
    from alembic import command

    from tests.conftest import alembic_config

    async def seed():
        owner = await account("cache-rollback-owner")
        async with async_session_factory() as db:
            chat = Chat(owner_id=owner, title="survives rollback")
            db.add(chat)
            await db.flush()
            db.add(
                PrivateLlmWindowExtraction(
                    chat_id=chat.id,
                    input_hash="a" * 64,
                    field="synthetic",
                    prompt_version="test",
                    value={},
                )
            )
            await db.commit()
            return chat.id

    async def verify(chat_id):
        async with async_session_factory() as db:
            assert await db.get(Chat, chat_id) is not None
            assert (
                await db.scalar(select(func.count()).select_from(PrivateLlmWindowExtraction)) == 1
            )

    chat_id = asyncio.run(seed())
    with pytest.raises(RuntimeError, match="archive explicitly"):
        command.downgrade(alembic_config(), "0012_chat_pins")
    asyncio.run(verify(chat_id))
