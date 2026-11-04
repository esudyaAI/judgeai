import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from src.db import models  # noqa: F401  (registers tables on Base.metadata)
from src.db.base import Base
from tests.conftest import alembic_config


async def test_migrations_match_models():
    """`alembic upgrade head` must produce exactly the schema the models describe."""
    from src.db.session import engine

    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync_conn: compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)
        )
    assert diff == []


def test_downgrade_and_upgrade_roundtrip():
    cfg = alembic_config()
    command.downgrade(cfg, "0001")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_legal_library_downgrade_keeps_existing_case_data():
    import asyncio

    from src.db.models import Chat
    from src.db.session import async_session_factory

    async def create_case():
        async with async_session_factory() as db:
            chat = Chat(title="Case survives legal-library rollback")
            db.add(chat)
            await db.commit()
            return chat.id

    async def read_case(chat_id):
        async with async_session_factory() as db:
            from sqlalchemy import text

            return await db.scalar(text("SELECT title FROM chats WHERE id = :id"), {"id": chat_id})

    chat_id = asyncio.run(create_case())
    cfg = alembic_config()
    command.downgrade(cfg, "0002")
    try:
        assert asyncio.run(read_case(chat_id)) == "Case survives legal-library rollback"
    finally:
        command.upgrade(cfg, "head")
    assert asyncio.run(read_case(chat_id)) == "Case survives legal-library rollback"


def test_auth_backfill_and_rollback_preserve_old_case():
    import asyncio

    from sqlalchemy import text

    from src.db.session import async_session_factory

    async def execute(sql):
        async with async_session_factory() as db:
            result = await db.execute(text(sql))
            value = result.first() if result.returns_rows else None
            await db.commit()
            return value

    cfg = alembic_config()
    command.downgrade(cfg, "0004_criminal_article_sanctions")
    try:
        row = asyncio.run(
            execute("INSERT INTO chats (title) VALUES ('Legacy protected') RETURNING id")
        )
        command.upgrade(cfg, "head")
        owner = asyncio.run(
            execute(
                "SELECT u.username, u.is_active, u.password_hash FROM chats c "
                f"JOIN users u ON u.id = c.owner_id WHERE c.id = {int(row[0])}"
            )
        )
        assert tuple(owner) == ("__legacy_locked__", False, None)
        command.downgrade(cfg, "0004_criminal_article_sanctions")
        assert (
            asyncio.run(execute(f"SELECT title FROM chats WHERE id = {int(row[0])}"))[0]
            == "Legacy protected"
        )
    finally:
        command.upgrade(cfg, "head")


def test_defendant_cards_downgrade_keeps_the_first_card_and_the_verdict():
    import asyncio

    from sqlalchemy import text

    from src.db.session import async_session_factory

    async def execute(sql):
        async with async_session_factory() as db:
            result = await db.execute(text(sql))
            rows = result.all() if result.returns_rows else None
            await db.commit()
            return rows

    card = (
        "INSERT INTO precedent_cards (knowledge_verdict_id, defendant_no, text_sha256, "
        "qualification_keys, mitigating, aggravating, applied_general, conditional, episodes, "
        "fabula, extractor_version) VALUES ({v}, {n}, 'h', '{{}}', '{{}}', '{{}}', '{{}}', false, "
        "'[]', '', 'precedent-card/2')"
    )
    [(verdict_id,)] = asyncio.run(
        execute(
            "INSERT INTO knowledge_verdicts (raw_text, source_type, status) "
            "VALUES ('ruling', 'vsrf', 'indexed') "
            "RETURNING id"
        )
    )
    asyncio.run(execute(card.format(v=verdict_id, n=0)))
    asyncio.run(execute(card.format(v=verdict_id, n=1)))
    cfg = alembic_config()
    command.downgrade(cfg, "0008_precedent_embeddings")
    try:
        assert asyncio.run(execute("SELECT count(*) FROM precedent_cards"))[0][0] == 1
        assert asyncio.run(execute("SELECT count(*) FROM knowledge_verdicts"))[0][0] == 1
    finally:
        command.upgrade(cfg, "head")
    assert asyncio.run(execute("SELECT defendant_no FROM precedent_cards"))[0][0] == 0


def test_reports_downgrade_refuses_to_discard_saved_private_data():
    import asyncio

    import pytest
    from sqlalchemy import text

    from src.db.session import async_session_factory

    async def seed():
        async with async_session_factory() as db:
            owner = await db.scalar(text("SELECT id FROM users LIMIT 1"))
            if owner is None:
                owner = await db.scalar(
                    text(
                        "INSERT INTO users (username, is_active, is_admin) "
                        "VALUES ('synthetic-report-owner', false, false) RETURNING id"
                    )
                )
            chat = await db.scalar(
                text(
                    "INSERT INTO chats (owner_id, title) VALUES (:owner, 'synthetic') RETURNING id"
                ),
                {"owner": owner},
            )
            message = await db.scalar(
                text(
                    "INSERT INTO messages (chat_id, role, status) "
                    "VALUES (:chat, 'assistant', 'completed') RETURNING id"
                ),
                {"chat": chat},
            )
            await db.execute(
                text(
                    "INSERT INTO case_reports (id, owner_id, chat_id, source_message_id, version, "
                    "snapshot, snapshot_sha256, docx_data, docx_sha256, created_at) VALUES "
                    "('00000000-0000-4000-8000-000000000014', :owner, :chat, :message, 1, "
                    "'{}', 'synthetic', :artifact, 'synthetic', now())"
                ),
                {"owner": owner, "chat": chat, "message": message, "artifact": b"PKsynthetic"},
            )
            await db.commit()

    async def count():
        async with async_session_factory() as db:
            return await db.scalar(text("SELECT count(*) FROM case_reports"))

    asyncio.run(seed())
    with pytest.raises(RuntimeError, match="archive explicitly"):
        command.downgrade(alembic_config(), "0013_private_window_cache")
    assert asyncio.run(count()) == 1


@pytest.mark.parametrize("private", [False, True])
def test_window_provenance_downgrade_refuses_to_discard_metadata(private):
    import asyncio

    import pytest
    from sqlalchemy import select

    from src.db.llm_window_extractions import PrivateLlmWindowExtraction
    from src.db.models import Chat, LlmWindowExtraction
    from src.db.session import async_session_factory
    from tests.test_auth import account

    async def seed():
        async with async_session_factory() as db:
            kwargs = {}
            if private:
                owner = await account("private-provenance-rollback")
                chat = Chat(owner_id=owner, title="synthetic")
                db.add(chat)
                await db.flush()
                kwargs["chat_id"] = chat.id
            model = PrivateLlmWindowExtraction if private else LlmWindowExtraction
            row = model(
                input_hash="a" * 64,
                field="synthetic",
                prompt_version="test",
                value={"kind": "fine"},
                provenance={"schema_version": 1},
                **kwargs,
            )
            db.add(row)
            await db.commit()

    async def verify():
        async with async_session_factory() as db:
            model = PrivateLlmWindowExtraction if private else LlmWindowExtraction
            row = await db.scalar(select(model))
            assert row.value == {"kind": "fine"} and row.provenance == {"schema_version": 1}

    asyncio.run(seed())
    with pytest.raises(RuntimeError, match="archive explicitly"):
        command.downgrade(alembic_config(), "0014_case_reports")
    asyncio.run(verify())


def test_legacy_window_values_survive_nullable_provenance_roundtrip():
    import asyncio

    from sqlalchemy import select, text

    from src.db.models import LlmWindowExtraction
    from src.db.session import async_session_factory

    async def seed():
        async with async_session_factory() as db:
            db.add(
                LlmWindowExtraction(
                    input_hash="b" * 64,
                    field="synthetic",
                    prompt_version="test",
                    value={"kind": "fine"},
                    provenance=None,
                )
            )
            await db.commit()
            assert await db.scalar(text("SELECT provenance IS NULL FROM llm_window_extractions"))

    async def verify():
        async with async_session_factory() as db:
            row = await db.scalar(select(LlmWindowExtraction))
            assert row.value == {"kind": "fine"} and row.provenance is None

    asyncio.run(seed())
    command.downgrade(alembic_config(), "0014_case_reports")
    command.upgrade(alembic_config(), "head")
    asyncio.run(verify())


def test_analysis_revisions_downgrade_preserves_populated_history():
    import asyncio
    from uuid import UUID

    from src.db.analysis_revisions import AnalysisRevision
    from src.db.models import Chat, Message
    from src.db.session import async_session_factory
    from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
    from tests.test_auth import account

    async def seed():
        owner = await account("revision-rollback")
        async with async_session_factory() as db:
            chat = Chat(owner_id=owner, title="synthetic")
            db.add(chat)
            await db.flush()
            message = Message(chat_id=chat.id, role="assistant", status="completed")
            db.add(message)
            await db.flush()
            row = await SqlAnalysisRevisionStore(db).append(
                owner,
                chat.id,
                message.id,
                {"schema_version": 1, "fabula": "Legacy preserved"},
                None,
                kind="legacy",
            )
            await db.commit()
            return str(row.id)

    async def verify(revision_id):
        async with async_session_factory() as db:
            row = await db.get(AnalysisRevision, UUID(revision_id))
            assert row.result["fabula"] == "Legacy preserved" and row.calculation_inputs is None

    revision_id = asyncio.run(seed())
    with pytest.raises(RuntimeError, match="Analysis revisions contain records"):
        command.downgrade(alembic_config(), "0015_window_provenance")
    asyncio.run(verify(revision_id))
