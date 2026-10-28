"""CLI of the sudact.ru crawler and importer.

crawl  - walk the sitemap /regular/doc/ pages, keep first-instance verdicts
         (robots gate, pacing, retries, resumable state, raw html cache).
import - load crawled verdicts into knowledge_verdicts (needs the api env).

Usage:
    python -m src.cli.sudact crawl --out data/sudact --workers 8 --rate 6
    python -m src.cli.sudact import --file data/sudact/verdicts.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def cmd_crawl(args: argparse.Namespace) -> int:
    # stdlib-only imports: the crawl runs without the api dependencies
    from src.application.sudact_crawl import CrawlSudact
    from src.infrastructure.sudact_html import parse_sudact_page
    from src.infrastructure.sudact_http import SudactFetcher
    from src.infrastructure.sudact_store import CrawlDirectoryBusy, SudactDiskStore

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        store = SudactDiskStore(Path(args.out))
    except CrawlDirectoryBusy as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    fetcher = SudactFetcher(
        user_agent=args.user_agent,
        rate_per_sec=args.rate,
        timeout=args.timeout,
        max_retries=args.retries,
    )
    urls = fetcher.sitemap_urls()
    log.info(
        "sitemap /regular/doc/ URLs: %d, already processed: %d",
        len(urls),
        len(store.done_urls),
    )

    crawl = CrawlSudact(
        fetcher,
        store,
        parse_sudact_page,
        workers=args.workers,
        cache_all=args.cache_all,
    )
    report = crawl.execute(
        urls,
        limit_pages=args.limit_pages,
        stop_after_verdicts=args.stop_after,
        state_every=args.state_every,
    )
    payload = {
        "pages": report.pages,
        "already_done": report.already_done,
        "verdicts": report.verdicts,
        "duplicates": report.duplicates,
        "skipped_kind": report.skipped_kind,
        "failed": report.failed,
        "robots_blocked": report.robots_blocked,
        "stop_reason": report.stop_reason,
        "current_rate": report.current_rate,
        "verdicts_total": store.stats.get("verdicts_saved", 0),
        "verdicts_path": str(store.verdicts_path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.robots_blocked == 0 else 2


def cmd_import(args: argparse.Namespace) -> int:
    from src.services.sudact_import import run_import_cli

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stats = run_import_cli(args.file)
    print(
        json.dumps(
            {
                "imported": stats.imported,
                "duplicates": stats.duplicates,
                "empty_text": stats.empty_text,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sudact", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="crawl sudact.ru via the sitemap")
    crawl.add_argument("--out", default="data/sudact", help="crawl output directory")
    crawl.add_argument("--workers", type=int, default=8)
    crawl.add_argument("--rate", type=float, default=6.0, help="requests per second ceiling")
    crawl.add_argument("--timeout", type=float, default=30.0)
    crawl.add_argument("--retries", type=int, default=4)
    crawl.add_argument("--limit-pages", type=int, help="stop after N new pages fetched")
    crawl.add_argument("--stop-after", type=int, help="stop after N verdicts saved in total")
    crawl.add_argument("--state-every", type=int, default=200)
    crawl.add_argument(
        "--cache-all",
        action="store_true",
        help="cache raw html of every page, not only verdicts",
    )
    crawl.add_argument(
        "--user-agent",
        default="JudgeAI-Crawler/0.1 (+https://esudya.ru)",
        help="honest UA; set a real contact before heavy crawls",
    )
    crawl.set_defaults(func=cmd_crawl)

    imp = sub.add_parser("import", help="import crawled verdicts into the knowledge base")
    imp.add_argument("--file", default="data/sudact/verdicts.jsonl")
    imp.set_defaults(func=cmd_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
