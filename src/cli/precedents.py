"""Build precedent cards and fabula vectors from verdicts of the knowledge base.

Usage: python -m src.cli.precedents index
Idempotent: verdicts that already have a card and texts that already have a vector are skipped.
With --chunks, knowledge-base chunks without a vector of the configured EMBEDDING_MODEL are
embedded too (the fallback search only; costly with a cloud model).
"""

import argparse
import asyncio
import json
from dataclasses import asdict

from src.application.precedent_cards import CARD_EXTRACTOR_VERSION
from src.application.precedent_refresh import refresh_precedents
from src.application.similar_precedents import IndexPrecedents
from src.db.session import async_session_factory
from src.infrastructure.fastembed_embedder import FastembedEmbedder
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import PracticeReader
from src.services.knowledge_service import reembed_knowledge_chunks


async def run_index(embedder=None, chunks: bool = False) -> dict:
    async with async_session_factory() as db:
        use_case = IndexPrecedents(
            SqlPrecedentStore(db), PracticeReader(), embedder or FastembedEmbedder()
        )
        report = asdict(await use_case.execute(CARD_EXTRACTOR_VERSION))
    if chunks:
        report["knowledge_chunks"] = await _reembed_chunks()
    return report


async def _reembed_chunks() -> int | str:
    async with async_session_factory() as db:
        try:
            done = await reembed_knowledge_chunks(db)
        except Exception as exc:  # cards and their vectors above are already saved
            await db.rollback()
            return f"{type(exc).__name__}: {exc}"
        await db.commit()
        return done


async def run_refresh(apply: bool = False) -> dict:
    async with async_session_factory() as db:
        report = await refresh_precedents(
            SqlPrecedentStore(db), PracticeReader(), CARD_EXTRACTOR_VERSION, apply=apply
        )
        return asdict(report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="build missing cards and vectors")
    index.add_argument(
        "--chunks",
        action="store_true",
        help="also re-embed knowledge-base chunks (used only by the fallback search)",
    )
    refresh = commands.add_parser(
        "refresh-cards", help="review/rebuild stale derived cards without vector API calls"
    )
    refresh.add_argument(
        "--apply", action="store_true", help="explicitly apply the refresh; default is dry-run"
    )
    args = parser.parse_args()
    report = (
        asyncio.run(run_refresh(args.apply))
        if args.command == "refresh-cards"
        else asyncio.run(run_index(chunks=args.chunks))
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
