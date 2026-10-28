"""Adapter: urllib fetcher for sudact.ru with robots gate, pacing and retries.

The fetcher is deliberately stdlib-only so the crawl runs anywhere without
project dependencies. Politeness contract (docs/data-sources.md):

* robots.txt is fetched once and every URL is checked against it;
* a token-bucket limiter paces requests across all worker threads;
* 429/5xx/network errors are retried with exponential backoff; the global
  pace is halved after throttling and slowly recovers afterwards;
* 404/410 are terminal, never retried.

Measured 28.10: the site answers ~0.5 s p50 with concurrency 8 and no
Crawl-delay in robots; defaults are conservative below that (6 rps).
"""

from __future__ import annotations

import gzip
import logging
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser

from src.application.sudact_crawl import FetchResult

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "JudgeAI-Crawler/0.1 (+https://esudya.ru)"
BASE = "https://sudact.ru"
SITEMAP_INDEX = f"{BASE}/sitemap.xml"
SITEMAP_LOC_RE = r"<loc>([^<]+)</loc>"
DOC_URL_RE = r"^https://sudact\.ru/regular/doc/[\w-]+/?$"

_TERMINAL_STATUSES = frozenset({404, 410})


class RateLimiter:
    """Thread-safe pacer: one permission every ``interval`` seconds."""

    def __init__(self, rate_per_sec: float) -> None:
        self._interval = 1.0 / max(rate_per_sec, 0.1)
        self._lock = threading.Lock()
        self._next_at = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_at)
            self._next_at = start + self._interval
            wait = start - now
        if wait > 0:
            time.sleep(wait)

    def halve_rate(self, floor: float = 0.5) -> float:
        """Throttling response: double the interval (not below the floor)."""
        with self._lock:
            self._interval = min(2.0, max(self._interval * 2.0, 1.0 / floor))
            return 1.0 / self._interval

    def recover(self, ceiling: float) -> None:
        """Successful stretch: nudge the interval back toward the ceiling."""
        with self._lock:
            target = 1.0 / ceiling
            self._interval = max(target, self._interval * 0.95)
            return None

    @property
    def current_rate(self) -> float:
        with self._lock:
            return 1.0 / self._interval


class SudactFetcher:
    """Fetches sitemap entries and document pages from sudact.ru."""

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_per_sec: float = 6.0,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_base: float = 5.0,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_base = backoff_base
        self.rate_ceiling = rate_per_sec
        self.limiter = RateLimiter(rate_per_sec)
        self._robots: urllib.robotparser.RobotFileParser | None = None
        self._robots_lock = threading.Lock()
        self._success_since_throttle = 0

    # -- robots ---------------------------------------------------------

    def robots(self) -> urllib.robotparser.RobotFileParser:
        if self._robots is None:
            with self._robots_lock:
                if self._robots is None:
                    parser = urllib.robotparser.RobotFileParser()
                    body = self._fetch_robots()
                    parser.parse(body.decode("utf-8", errors="replace"))
                    self._robots = parser
        return self._robots

    def _fetch_robots(self) -> bytes:
        last: Exception | None = None
        for attempt in range(3):
            try:
                return self._open(f"{BASE}/robots.txt")
            except Exception as exc:  # pragma: no cover - network resilience
                last = exc
                time.sleep(self.backoff_base * (2**attempt))
        raise RuntimeError(f"robots.txt unavailable after retries: {last}")

    def robots_allows(self, url: str) -> bool:
        try:
            return self.robots().can_fetch(self.user_agent, url)
        except Exception as exc:  # robots unreachable: do not crawl blindly
            log.warning("robots.txt unavailable, refusing to fetch: %s", exc)
            return False

    # -- fetching -------------------------------------------------------

    def _open(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
            return self._maybe_gunzip(body)

    @staticmethod
    def _maybe_gunzip(body: bytes) -> bytes:
        # servers may answer .gz sitemap parts with plain xml: trust magic bytes
        return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body

    def fetch(self, url: str) -> FetchResult:
        """Fetch one URL with pacing, retries and backoff."""
        if not self.robots_allows(url):
            return FetchResult(url, 0, None, "robots_disallowed", 0)

        attempts = 0
        while True:
            attempts += 1
            self.limiter.acquire()
            try:
                body = self._open(url)
                self._note_success()
                return FetchResult(url, 200, body, None, attempts)
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status in _TERMINAL_STATUSES:
                    return FetchResult(url, status, None, f"http_{status}", attempts)
                if attempts > self.max_retries:
                    return FetchResult(url, status, None, f"http_{status}", attempts)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                self._note_throttle(status)
                self._sleep_backoff(attempts, retry_after)
            except Exception as exc:
                if attempts > self.max_retries:
                    return FetchResult(url, 0, None, f"{type(exc).__name__}: {exc}", attempts)
                self._sleep_backoff(attempts)

    def _note_success(self) -> None:
        self._success_since_throttle += 1
        if self._success_since_throttle >= 200:
            self._success_since_throttle = 0
            self.limiter.recover(self.rate_ceiling)

    def _note_throttle(self, status: int) -> None:
        self._success_since_throttle = 0
        rate = self.limiter.halve_rate()
        log.warning("HTTP %s: pace reduced to %.2f rps", status, rate)

    def _sleep_backoff(self, attempts: int, retry_after: str | None = None) -> None:
        if retry_after:
            try:
                time.sleep(max(float(retry_after), 1.0))
                return
            except ValueError:
                pass
        time.sleep(self.backoff_base * (2 ** (attempts - 1)))

    # -- sitemap --------------------------------------------------------

    def sitemap_urls(self) -> list[str]:
        """All /regular/doc/ URLs from both sitemap parts."""
        import re

        index = self._open(SITEMAP_INDEX).decode("utf-8", errors="replace")
        parts = re.findall(SITEMAP_LOC_RE, index)
        urls: list[str] = []
        for part in parts:
            body = self._open(part)
            text = self._maybe_gunzip(body).decode("utf-8", errors="replace")
            urls += re.findall(SITEMAP_LOC_RE, text)
        doc_re = re.compile(DOC_URL_RE)
        return [u for u in urls if doc_re.match(u)]
