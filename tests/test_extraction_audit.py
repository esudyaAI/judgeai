from sqlalchemy import func, select

from src.cli.precedent_audit import database_sources
from src.db.models import KnowledgeVerdict
from src.db.precedents import PrecedentCardRow
from src.db.session import async_session_factory


async def test_database_audit_is_read_only_and_excludes_private_sources():
    async with async_session_factory() as db:
        db.add_all(
            [
                KnowledgeVerdict(
                    raw_text="Public practice text",
                    source_type="sudact",
                    structured={"source_url": "https://example.test/1"},
                ),
                KnowledgeVerdict(raw_text="Private case text", source_type="chat"),
                KnowledgeVerdict(raw_text="", source_type="manual"),
            ]
        )
        await db.commit()
    sources = await database_sources()
    assert len(sources) == 2
    assert {s.text for s in sources} == {"Public practice text", ""}
    assert all(s.source_type != "chat" for s in sources)
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(KnowledgeVerdict)) == 3
        assert await db.scalar(select(func.count()).select_from(PrecedentCardRow)) == 0
