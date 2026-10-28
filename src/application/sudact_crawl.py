"""Use case: crawl sudact.ru document pages and keep first-instance verdicts.

Orchestration only: the fetcher port does robots/pacing/retries, the parser
port turns bytes into a domain document, the sink port persists everything.
Stopping rules (page limit, verdict target) are checked between completions.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from src.domain.sudact import KEEP_KINDS, SudactDocument

log = logging.getLogger(__name__)

DocumentParser = Callable[[str, bytes], SudactDocument]


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one port fetch: 200 with body, or a failure reason."""

    url: str
    status: int
    body: bytes | None
    error: str | None
    attempts: int


class SudactFetcherPort(Protocol):
    def robots_allows(self, url: str) -> bool: ...

    def fetch(self, url: str) -> FetchResult: ...


class DocumentSinkPort(Protocol):
    def is_processed(self, url: str) -> bool: ...

    def seen(self, key: str) -> bool: ...

    def save_raw(self, html_sha256: str, body: bytes): ...

    def save_verdict(self, doc: SudactDocument, raw_path) -> bool: ...

    def mark_done(self, url: str) -> None: ...

    def mark_failed(self, url: str, reason: str) -> None: ...

    def save_state(self) -> None: ...


@dataclass
class CrawlReport:
    pages: int = 0
    already_done: int = 0
    verdicts: int = 0
    duplicates: int = 0
    skipped_kind: int = 0
    failed: int = 0
    robots_blocked: int = 0
    stop_reason: str = "exhausted"
    current_rate: float = 0.0


class CrawlSudact:
    def __init__(
        self,
        fetcher: SudactFetcherPort,
        sink: DocumentSinkPort,
        parser: DocumentParser,
        keep_kinds: frozenset[str] = KEEP_KINDS,
        workers: int = 8,
        cache_all: bool = False,
    ) -> None:
        self.fetcher = fetcher
        self.sink = sink
        self.parser = parser
        self.keep_kinds = keep_kinds
        self.workers = max(1, workers)
        self.cache_all = cache_all
        self._lock = threading.Lock()

    def execute(
        self,
        urls: list[str],
        limit_pages: int | None = None,
        stop_after_verdicts: int | None = None,
        state_every: int = 200,
    ) -> CrawlReport:
        """Crawl in waves of ``workers`` URLs: stopping rules are checked
        between waves, so an overshoot stays bounded by one in-flight wave."""
        report = CrawlReport()
        verdicts_total = (
            self.sink.stats.get("verdicts_saved", 0) if hasattr(self.sink, "stats") else 0
        )
        stop = threading.Event()
        todo = [u for u in urls if not self.sink.is_processed(u)]
        report.already_done = len(urls) - len(todo)

        def work(url: str) -> None:
            if stop.is_set():
                return
            self._process(url, report)

        processed = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            start = 0
            while start < len(todo) and not stop.is_set():
                wave = todo[start : start + self.workers]
                futures = [pool.submit(work, url) for url in wave]
                for future in as_completed(futures):
                    future.result()
                    processed += 1
                    if processed % state_every == 0:
                        self.sink.save_state()
                        self._log_progress(report, verdicts_total)
                start += len(wave)
                if limit_pages is not None and report.pages >= limit_pages:
                    report.stop_reason = "limit_pages"
                    stop.set()
                if stop_after_verdicts is not None and (
                    verdicts_total + report.verdicts >= stop_after_verdicts
                ):
                    report.stop_reason = "stop_after_verdicts"
                    stop.set()
        self.sink.save_state()
        rate = getattr(self.fetcher, "limiter", None)
        report.current_rate = rate.current_rate if rate else 0.0
        return report

    def _process(self, url: str, report: CrawlReport) -> None:
        try:
            result = self.fetcher.fetch(url)
        except Exception as exc:  # the fetcher already retried; count and move on
            log.warning("fetch %s raised %s", url, exc)
            self.sink.mark_failed(url, f"{type(exc).__name__}: {exc}")
            with self._lock:
                report.failed += 1
            return

        if result.status == 0 and result.error == "robots_disallowed":
            self.sink.mark_failed(url, "robots_disallowed")
            with self._lock:
                report.robots_blocked += 1
            return
        if result.status != 200 or result.body is None:
            reason = result.error or f"http_{result.status}"
            if result.status in (404, 410):
                self.sink.mark_done(url)  # terminal, do not retry next run
            else:
                self.sink.mark_failed(url, reason)
            with self._lock:
                report.failed += 1
            return

        doc = self.parser(url, result.body)
        raw_path = None
        if doc.act_kind in self.keep_kinds or self.cache_all:
            raw_path = self.sink.save_raw(doc.html_sha256, result.body)
        self.sink.mark_done(url)
        with self._lock:
            report.pages += 1
        if doc.act_kind not in self.keep_kinds:
            with self._lock:
                report.skipped_kind += 1
            return
        if self.sink.seen(doc.dedup_key):
            with self._lock:
                report.duplicates += 1
            return
        if self.sink.save_verdict(doc, raw_path):
            with self._lock:
                report.verdicts += 1

    def _log_progress(self, report: CrawlReport, verdicts_total: int) -> None:
        log.info(
            "pages=%d verdicts=%d (+%d dup) skipped=%d failed=%d total_verdicts=%d",
            report.pages,
            report.verdicts,
            report.duplicates,
            report.skipped_kind,
            report.failed,
            verdicts_total + report.verdicts,
        )
