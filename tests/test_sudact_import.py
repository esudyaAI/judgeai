"""Importing crawled sudact verdicts: rows, chunks, provenance and cards.

The import writes KnowledgeVerdict rows (source_type=sudact) without
embeddings; the existing card pipeline then reads raw_text and keeps the
origin URL from the structured field.
"""

import hashlib

from sqlalchemy import func, select

from src.application.precedent_cards import CARD_EXTRACTOR_VERSION
from src.application.similar_precedents import IndexPrecedents
from src.db.models import KnowledgeChunk, KnowledgeVerdict
from src.db.precedents import PrecedentCardRow
from src.db.session import async_session_factory
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import RegexVerdictReader
from src.services.sudact_import import import_verdicts
from tests.fixtures.fake_embedder import HashingEmbedder
from tests.fixtures.synthetic_verdicts import PRACTICE_ROBBERY, PRACTICE_THEFT


def _record(text: str, uid: str, url: str) -> dict:
    return {
        "url": url,
        "fetched_at": "2026-10-28T10:00:00+00:00",
        "title": "Приговор № 1-1/2026",
        "act_kind": "приговор",
        "case_number": "1-1/2026",
        "uid": uid,
        "court_name": "Условный районный суд г. Примерска",
        "decision_date": "2026-05-12",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "articles": ["158"],
        "raw_path": "data/sudact/raw/x.html",
    }


THEFT_RECORD = _record(
    PRACTICE_THEFT, "21RS0001-01-2026-000001-01", "https://sudact.ru/regular/doc/theft/"
)
ROBBERY_RECORD = _record(
    PRACTICE_ROBBERY, "21RS0002-01-2026-000002-02", "https://sudact.ru/regular/doc/robbery/"
)


async def test_import_creates_rows_chunks_and_provenance():
    async with async_session_factory() as db:
        stats = await import_verdicts(db, [THEFT_RECORD, ROBBERY_RECORD])
    assert stats.imported == 2
    async with async_session_factory() as db:
        verdicts = {
            v.uid: v
            for v in await db.scalars(
                select(KnowledgeVerdict).where(KnowledgeVerdict.source_type == "sudact")
            )
        }
    assert set(verdicts) == {THEFT_RECORD["uid"], ROBBERY_RECORD["uid"]}
    theft = verdicts[THEFT_RECORD["uid"]]
    assert theft.court_name == "Условный районный суд г. Примерска"
    assert str(theft.verdict_date) == "2026-05-12"
    assert theft.source_filename == "theft"
    assert theft.structured["source_url"] == "https://sudact.ru/regular/doc/theft/"
    assert theft.structured["fetched_at"] == "2026-10-28T10:00:00+00:00"
    assert theft.status == "indexed_no_vectors"
    async with async_session_factory() as db:
        chunk_count = await db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .join(KnowledgeVerdict, KnowledgeChunk.verdict_id == KnowledgeVerdict.id)
            .where(KnowledgeVerdict.source_type == "sudact")
        )
    assert chunk_count > 0
    # chunks have no vectors: embeddings are added later, not by the bulk import
    async with async_session_factory() as db:
        embedded = await db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.embedding.is_not(None))
        )
        assert list(embedded) == []


async def test_reimport_is_idempotent_by_uid_and_hash():
    async with async_session_factory() as db:
        await import_verdicts(db, [THEFT_RECORD])
    async with async_session_factory() as db:
        same_text_other_url = dict(THEFT_RECORD, url="https://sudact.ru/regular/doc/again/")
        stats = await import_verdicts(db, [same_text_other_url])
    assert stats.imported == 0
    assert stats.duplicates == 1
    async with async_session_factory() as db:
        total = await db.scalar(
            select(func.count())
            .select_from(KnowledgeVerdict)
            .where(KnowledgeVerdict.source_type == "sudact")
        )
    assert total == 1


async def test_empty_text_records_are_counted_not_imported():
    async with async_session_factory() as db:
        stats = await import_verdicts(db, [dict(THEFT_RECORD, text=" ")])
    assert stats.imported == 0
    assert stats.empty_text == 1


async def test_import_jsonl_reads_file_and_is_idempotent(tmp_path):
    path = tmp_path / "verdicts.jsonl"
    lines = [dict(THEFT_RECORD, uid="21RS0009-01-2026-000009-09"), dict(ROBBERY_RECORD)]
    path.write_text(
        "\n".join(__import__("json").dumps(line, ensure_ascii=False) for line in lines),
        encoding="utf-8",
    )
    from src.db.session import async_session_factory
    from src.services.sudact_import import import_jsonl

    first = await import_jsonl(path, async_session_factory)
    second = await import_jsonl(path, async_session_factory)
    assert first.imported == 2
    assert second.imported == 0
    assert second.duplicates == 2


async def test_cards_are_built_with_provenance_url():
    async with async_session_factory() as db:
        await import_verdicts(db, [THEFT_RECORD, ROBBERY_RECORD])
    async with async_session_factory() as db:
        index = IndexPrecedents(SqlPrecedentStore(db), RegexVerdictReader(), HashingEmbedder())
        report = await index.execute(CARD_EXTRACTOR_VERSION)
    assert report.cards == 2
    assert report.vectors >= 1  # one vector per distinct fabula text
    async with async_session_factory() as db:
        cards = await db.scalars(select(PrecedentCardRow).order_by(PrecedentCardRow.id))
        card_list = list(cards)
    by_url = {c.source_url: c for c in card_list}
    assert by_url["https://sudact.ru/regular/doc/theft/"].uid == THEFT_RECORD["uid"]
    assert by_url["https://sudact.ru/regular/doc/robbery/"].main_article == "161"
    assert by_url["https://sudact.ru/regular/doc/theft/"].court_name == (
        "Условный районный суд г. Примерска"
    )
