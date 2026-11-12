"""Prepare and import a locally archived official legal document; link check rules to it.

Run --help for arguments. This command never certifies the legal edition or dates.
"""

import argparse
import asyncio
import io
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

from src.schemas.legal_library import ActImport, ProvisionImport, SnapshotImport
from src.services.legal_library import MAX_SOURCE_BYTES, import_snapshot
from src.services.legal_rule_catalog import link_rule
from src.services.legal_source_parser import (
    PARSER_VERSION,
    extract_html,
    extract_mhtml,
    split_articles,
)


def read_source(path: Path) -> bytes:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source file exceeds byte limit")
    return path.read_bytes()


def prepare(args):
    if args.source.resolve() == args.manifest.resolve():
        raise ValueError("manifest must not overwrite the source archive")
    raw = read_source(args.source)
    if args.format == "pravo-export":
        text = extract_mhtml(raw)
        provisions = split_articles(text)
    elif args.format == "kremlin":
        text = extract_html(raw.decode("utf-8"), article_body=True)
        provisions = split_articles(text)
    else:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if len(pdf.pages) > 1000:
                raise ValueError("source PDF exceeds page limit")
            pages = [page.extract_text() or "" for page in pdf.pages]
        if not pages or any(not text.strip() for text in pages):
            raise ValueError("PDF has unreadable pages; manual review required")
        text = "\n\f\n".join(pages)
        provisions = [
            ProvisionImport(
                locator=f"page.{i}",
                title=f"Page {i}",
                body=body,
                ordinal=i - 1,
                start_page=i,
                end_page=i,
            )
            for i, body in enumerate(pages, 1)
        ]
    snapshot = SnapshotImport(
        act=ActImport(
            key=args.key,
            title=args.title,
            kind=args.kind,
            number=args.number,
            adopted_on=args.adopted_on,
        ),
        source_url=args.source_url,
        raw_sha256=sha256(raw).hexdigest(),
        retrieved_at=args.retrieved_at,
        edition_label=args.edition_label,
        full_text=text,
        parser_version=PARSER_VERSION + ":" + args.format,
        provisions=provisions,
    )
    args.manifest.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"Prepared {snapshot.act.key}: {len(provisions)} units, "
        f"{len(text)} characters; legal verification pending"
    )


async def run_import(args):
    from src.db.session import async_session_factory

    if args.manifest.stat().st_size > 40 * 1024 * 1024:
        raise ValueError("manifest exceeds byte limit")
    manifest = SnapshotImport.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    raw = read_source(args.source)
    async with async_session_factory() as db, db.begin():
        edition, created = await import_snapshot(db, manifest, raw)
    print(
        f"Edition {edition.id}: {'imported' if created else 'already present'}; "
        f"status={edition.verification_status}"
    )


async def run_link_rule(args):
    from sqlalchemy import select

    from src.db.models import LegalEdition
    from src.db.session import async_session_factory

    async with async_session_factory() as db, db.begin():
        _, created = await link_rule(
            db, args.rule, args.act, args.edition, args.locator, args.rationale
        )
        status = await db.scalar(
            select(LegalEdition.verification_status).where(LegalEdition.id == args.edition)
        )
    print(
        f"Rule {args.rule} -> {args.act} {args.locator} (edition {args.edition}): "
        f"{'linked' if created else 'already linked'}; status={status}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source", type=Path, required=True)
    prep.add_argument("--manifest", type=Path, required=True)
    prep.add_argument("--format", choices=["pravo-export", "kremlin", "pdf"], required=True)
    prep.add_argument("--source-url", required=True)
    prep.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    prep.add_argument("--key", required=True)
    prep.add_argument("--title", required=True)
    prep.add_argument("--kind", required=True)
    prep.add_argument("--number")
    prep.add_argument("--adopted-on", type=date.fromisoformat)
    prep.add_argument("--edition-label", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--source", type=Path, required=True)
    imp.add_argument("--manifest", type=Path, required=True)
    link = sub.add_parser("link-rule", help="link a legal_core rule to a stored provision")
    link.add_argument("--rule", required=True)
    link.add_argument("--act", required=True)
    link.add_argument("--edition", type=int, required=True)
    link.add_argument("--locator", required=True)
    link.add_argument("--rationale", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "link-rule":
        asyncio.run(run_link_rule(args))
    else:
        asyncio.run(run_import(args))


if __name__ == "__main__":
    main()
