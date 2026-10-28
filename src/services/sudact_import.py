"""Service: import crawled sudact.ru verdicts into the knowledge base.

Records from the crawler (verdicts.jsonl) become KnowledgeVerdict rows with
source_type="sudact": raw_text feeds the precedent-card pipeline, chunks feed
the keyword fallback search. Chunks are stored without embeddings - the
embedding model may be unavailable during bulk import; vectors are added later
by the same background path as for manual uploads.

Provenance (AUTORUN rule 0): source_url, fetched_at, raw_path, sha256 and the
original title are kept in the structured field, because knowledge_verdicts
has no dedicated url column and T6.1 adds no migrations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import KnowledgeChunk, KnowledgeVerdict
from src.services.knowledge_service import build_chunks

log = logging.getLogger(__name__)

SUDACT_SOURCE_TYPE = "sudact"

_STRUCT_FIELDS = ("source_url", "fetched_at", "raw_path", "title", "region", "act_kind", "articles")


@dataclass(frozen=True)
class ImportStats:
    imported: int = 0
    duplicates: int = 0
    empty_text: int = 0


def _decision_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] or "sudact"


def record_fields(record: dict) -> dict:
    """Crawl record -> constructor kwargs of KnowledgeVerdict (pure)."""
    text = record.get("text") or ""
    structured = {key: record.get(key) for key in _STRUCT_FIELDS if record.get(key) is not None}
    if record.get("url"):
        structured["source_url"] = record["url"]
    return {
        "uid": record.get("uid"),
        "case_number": record.get("case_number"),
        "court_name": record.get("court_name"),
        "verdict_date": _decision_date(record.get("decision_date")),
        "source_type": SUDACT_SOURCE_TYPE,
        "source_filename": _slug(record.get("url") or ""),
        "file_hash": record.get("text_sha256"),
        "raw_text": text,
        "structured": structured,
        "status": "indexed" if text.strip() else "empty",
    }


async def _existing(
    db: AsyncSession, uid: str | None, file_hash: str | None
) -> KnowledgeVerdict | None:
    if uid:
        row = await db.scalar(select(KnowledgeVerdict).where(KnowledgeVerdict.uid == uid))
        if row:
            return row
    if file_hash:
        return await db.scalar(
            select(KnowledgeVerdict).where(KnowledgeVerdict.file_hash == file_hash)
        )
    return None


async def import_verdicts(
    db: AsyncSession, records: list[dict], commit_every: int = 50
) -> ImportStats:
    imported = duplicates = empty_text = 0
    for index, record in enumerate(records, start=1):
        fields = record_fields(record)
        if not fields["raw_text"].strip():
            empty_text += 1
            continue
        existing = await _existing(db, fields["uid"], fields["file_hash"])
        if existing is not None:
            duplicates += 1
            continue
        verdict = KnowledgeVerdict(**fields)
        try:
            # savepoint: a concurrent duplicate only rolls back this record
            async with db.begin_nested():
                db.add(verdict)
                await db.flush()
        except IntegrityError:
            duplicates += 1
            continue
        for chunk_text in build_chunks(fields["raw_text"]):
            db.add(
                KnowledgeChunk(
                    verdict_id=verdict.id, chunk_type="text", content=chunk_text, embedding=None
                )
            )
        if verdict.status == "indexed":
            verdict.status = "indexed_no_vectors"
        imported += 1
        if index % commit_every == 0:
            await db.commit()
            log.info("sudact import: %d processed, %d imported", index, imported)
    await db.commit()
    return ImportStats(imported, duplicates, empty_text)


async def import_jsonl(path, db_factory) -> ImportStats:
    """Read a crawl verdicts.jsonl and import every record."""
    import json
    from pathlib import Path

    records: list[dict] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    async with db_factory() as db:
        stats = await import_verdicts(db, records)
    return stats


def run_import_cli(path: str) -> ImportStats:
    from src.db.session import async_session_factory

    return asyncio.run(import_jsonl(path, async_session_factory))
