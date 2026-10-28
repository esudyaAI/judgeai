"""Test setup: separate judgeai_test database migrated by Alembic, fake LLM, no model downloads.

Run inside the api container:  docker compose run --rm api pytest
"""

import asyncio
import os
import tempfile

# Must be set before anything imports src.config.
os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "judgeai_test")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["LLM_ALLOW_FAKE"] = "true"
os.environ["DB_NULL_POOL"] = "true"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="judgeai-test-uploads-")

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from src.config import settings  # noqa: E402

ALEMBIC_INI = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")


async def _recreate_database() -> None:
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database="postgres",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{settings.POSTGRES_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}"')
    finally:
        await conn.close()


def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


def pytest_sessionstart(session):
    assert settings.POSTGRES_DB.endswith("_test"), (
        "refusing to run tests against a non-test database"
    )
    asyncio.run(_recreate_database())
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
async def clean_db():
    from src.db.session import engine

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE chats, knowledge_verdicts, legal_acts, users, auth_login_buckets, "
                "llm_window_extractions, precedent_embeddings "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture(autouse=True)
def no_embeddings(monkeypatch):
    """Embedding models are downloaded on first use; tests exercise the keyword fallback."""

    async def _fail(*_args, **_kwargs):
        raise RuntimeError("embeddings disabled in tests")

    monkeypatch.setattr("src.services.similarity_search.embed_query", _fail)
    monkeypatch.setattr("src.services.knowledge_service.embed_passages", _fail)
    monkeypatch.setattr("src.infrastructure.fastembed_embedder.embed_query", _fail)
    monkeypatch.setattr("src.infrastructure.fastembed_embedder.embed_passages", _fail)


@pytest.fixture
async def client():
    from src.db.auth import User
    from src.db.session import async_session_factory
    from src.main import app
    from src.services.auth import create_session
    from src.services.auth_tokens import csrf_for

    async with async_session_factory() as db:
        user = User(username="test-admin", is_admin=True)
        db.add(user)
        await db.commit()
        token = await create_session(db, user)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as c:
        c.cookies.set("judgeai_session", token)
        c.headers["X-CSRF-Token"] = csrf_for(token)
        yield c
