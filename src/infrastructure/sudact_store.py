"""Adapter: on-disk store of the sudact crawl.

Layout under the crawl directory:

* ``sitemap/``            cached sitemap parts (reused between runs);
* ``raw/<sha256>.html``   every fetched page, byte-for-byte (provenance);
* ``verdicts.jsonl``      one record per kept verdict, append-only;
* ``state.json``          processed/failed URL sets, counters (resume support).

The store is thread-safe: crawl workers save concurrently.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
from pathlib import Path

from src.domain.sudact import SudactDocument

log = logging.getLogger(__name__)


class CrawlDirectoryBusy(RuntimeError):
    """Another crawler process is already writing to this directory."""


class SudactDiskStore:
    def __init__(self, out_dir: Path, exclusive: bool = True) -> None:
        self.out_dir = Path(out_dir)
        self.raw_dir = self.out_dir / "raw"
        self.sitemap_dir = self.out_dir / "sitemap"
        self.verdicts_path = self.out_dir / "verdicts.jsonl"
        self.state_path = self.out_dir / "state.json"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.sitemap_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._process_lock = (self.out_dir / "crawl.lock").open("a+")
        try:
            if exclusive:
                fcntl.flock(self._process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._process_lock.close()
            raise CrawlDirectoryBusy(f"another crawl is already running in {self.out_dir}") from exc

        state = self._load_state()
        self.done_urls: set[str] = set(state.get("done_urls", []))
        self.failed: dict[str, str] = dict(state.get("failed", {}))
        self.stats: dict[str, int] = dict(state.get("stats", {}))
        self._seen_keys: set[str] = set(state.get("seen_keys", []))
        jsonl_keys = self._keys_from_verdicts()
        self._seen_keys |= jsonl_keys
        # verdicts.jsonl is the source of truth: a killed run loses its
        # unsaved stats, but the records are already on disk
        self.stats["verdicts_saved"] = max(self.stats.get("verdicts_saved", 0), len(jsonl_keys))

    # -- resume state ----------------------------------------------------

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            log.warning("state.json unreadable, starting with empty state")
            return {}

    def _keys_from_verdicts(self) -> set[str]:
        keys: set[str] = set()
        if not self.verdicts_path.exists():
            return keys
        with self.verdicts_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                keys.add(record.get("dedup_key") or f"sha:{record.get('text_sha256')}")
        return keys

    def save_state(self) -> None:
        payload = {
            "done_urls": sorted(self.done_urls),
            "failed": self.failed,
            "stats": self.stats,
            "seen_keys": sorted(self._seen_keys),
        }
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def close(self) -> None:
        """Release the process lock; safe to call more than once."""
        if getattr(self, "_process_lock", None) is not None:
            try:
                fcntl.flock(self._process_lock, fcntl.LOCK_UN)
            finally:
                self._process_lock.close()
                self._process_lock = None

    # -- crawl outputs ----------------------------------------------------

    def is_processed(self, url: str) -> bool:
        return url in self.done_urls

    def mark_done(self, url: str) -> None:
        with self._lock:
            self.done_urls.add(url)
            self.stats["pages_fetched"] = self.stats.get("pages_fetched", 0) + 1

    def mark_failed(self, url: str, reason: str) -> None:
        with self._lock:
            self.failed[url] = reason
            self.stats["pages_failed"] = self.stats.get("pages_failed", 0) + 1

    def seen(self, key: str) -> bool:
        return key in self._seen_keys

    def save_raw(self, html_sha256: str, body: bytes) -> Path:
        path = self.raw_dir / f"{html_sha256}.html"
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(body)
            os.replace(tmp, path)
        return path

    def save_verdict(self, doc: SudactDocument, raw_path: Path) -> bool:
        """Append the record; returns False for a duplicate."""
        record = doc.to_record()
        record["dedup_key"] = doc.dedup_key
        record["raw_path"] = str(raw_path)
        with self._lock:
            if doc.dedup_key in self._seen_keys:
                self.stats["verdict_duplicates"] = self.stats.get("verdict_duplicates", 0) + 1
                return False
            with self.verdicts_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._seen_keys.add(doc.dedup_key)
            self.stats["verdicts_saved"] = self.stats.get("verdicts_saved", 0) + 1
            return True

    # -- sitemap cache ------------------------------------------------------

    def sitemap_part_path(self, part_url: str) -> Path:
        return self.sitemap_dir / part_url.rsplit("/", 1)[-1]

    def sitemap_parts(self) -> list[Path]:
        return sorted(self.sitemap_dir.glob("*.xml.gz"))
