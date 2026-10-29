"""Offline read-only audit of all practice documents. No embeddings or LLM calls.

python -m src.cli.precedent_audit --file data/sudact/verdicts.jsonl --out data/audit/report.json
python -m src.cli.precedent_audit --database --out data/audit/report.json

Only --include-quotes writes source snippets to the local report. Stdout is counts only.
"""

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from src.application.extraction_audit import AuditSource, audit_sources
from src.infrastructure.verdict_reader import PracticeReader


def read_sources(path: Path) -> list[AuditSource]:
    sources = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                sources.append(
                    AuditSource(f"line:{line_number}", "", "sudact", input_error="InvalidJSON")
                )
                continue
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("text"), str)
                or not isinstance(record.get("source_type", "sudact"), str)
            ):
                sources.append(
                    AuditSource(f"line:{line_number}", "", "sudact", input_error="InvalidSource")
                )
                continue
            sources.append(
                AuditSource(
                    str(record.get("uid") or record.get("id") or f"line:{line_number}"),
                    record["text"],
                    record.get("source_type", "sudact"),
                    record.get("url") if isinstance(record.get("url"), str) else None,
                )
            )
    return sources


async def database_sources() -> list[AuditSource]:
    from sqlalchemy import select, text

    from src.db.models import KnowledgeVerdict
    from src.db.session import async_session_factory
    from src.domain.practice import PRIVATE_SOURCE_TYPES

    async with async_session_factory() as db:
        # PostgreSQL rejects writes in this transaction; no app tables are changed.
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        rows = await db.scalars(
            select(KnowledgeVerdict)
            .where(
                KnowledgeVerdict.source_type.not_in(PRIVATE_SOURCE_TYPES),
            )
            .order_by(KnowledgeVerdict.id)
        )
        return [
            AuditSource(
                str(row.id),
                row.raw_text or "",
                row.source_type,
                (row.structured or {}).get("source_url"),
            )
            for row in rows
        ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--database", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--include-quotes", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("output already exists; choose a new path to preserve the prior audit")
    sources = asyncio.run(database_sources()) if args.database else read_sources(args.file)
    report = audit_sources(PracticeReader(), sources, include_quotes=args.include_quotes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Reports can contain source quotes: create privately and never overwrite another audit.
    descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(asdict(report), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(report.summary, ensure_ascii=False))
    return 1 if report.summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
