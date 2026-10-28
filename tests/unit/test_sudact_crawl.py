"""The crawl use case against fake ports: keeping, dedup, failures, stopping."""

import tempfile
import unittest
from pathlib import Path

from src.application.sudact_crawl import CrawlSudact, FetchResult
from src.domain.sudact import SudactDocument
from src.infrastructure.sudact_store import SudactDiskStore

VERDICT_TEXT = "Дело № 1-1/2026 УИД 21RS0001-01-2026-000001-01 ПРИГОВОР УСТАНОВИЛ ПРИГОВОРИЛ"
VERDICT_TEXT_2 = "Дело № 1-2/2026 УИД 21RS0002-01-2026-000002-02 ПРИГОВОР УСТАНОВИЛ ПРИГОВОРИЛ"


def _verdict_doc(url: str, text: str, uid: str = "21RS0001-01-2026-000001-01") -> SudactDocument:
    import hashlib

    return SudactDocument(
        url=url,
        fetched_at="2026-10-28T00:00:00+00:00",
        html_sha256=hashlib.sha256((text + url).encode()).hexdigest(),
        title="Приговор",
        act_kind="приговор",
        case_number="1-1/2026",
        uid=uid,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def _decision_doc(url: str) -> SudactDocument:
    return SudactDocument(
        url=url,
        fetched_at="2026-10-28T00:00:00+00:00",
        html_sha256="d" * 64,
        title="Решение",
        act_kind="решение",
        text="гражданское",
        text_sha256="r" * 64,
    )


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchResult], docs: dict[str, SudactDocument]):
        self.pages = pages
        self.docs = docs
        self.fetched: list[str] = []

    def robots_allows(self, url: str) -> bool:
        return url not in ("https://sudact.ru/regular/doc/blocked/")

    def fetch(self, url: str) -> FetchResult:
        self.fetched.append(url)
        if url in self.pages:
            return self.pages[url]
        return FetchResult(url, 200, b"<html></html>", None, 1)


class FakeParser:
    def __init__(self, docs: dict[str, SudactDocument]):
        self.docs = docs

    def __call__(self, url: str, body: bytes) -> SudactDocument:
        return self.docs[url]


def _make(pages, docs):
    return FakeFetcher(pages, docs), FakeParser(docs)


class CrawlUseCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = SudactDiskStore(Path(self.tmp.name))

    def tearDown(self):
        self.sink.close()
        self.tmp.cleanup()

    def _crawl(self, fetcher, parser, urls, **kwargs):
        crawl = CrawlSudact(fetcher, self.sink, parser, workers=2)
        return crawl.execute(list(urls), **kwargs)

    def test_keeps_verdicts_and_skips_other_kinds(self):
        v1 = "https://sudact.ru/regular/doc/v1/"
        d1 = "https://sudact.ru/regular/doc/d1/"
        docs = {v1: _verdict_doc(v1, VERDICT_TEXT), d1: _decision_doc(d1)}
        fetcher, parser = _make({}, docs)
        report = self._crawl(fetcher, parser, docs.keys())
        self.assertEqual(report.verdicts, 1)
        self.assertEqual(report.skipped_kind, 1)
        self.assertEqual(self.sink.stats["verdicts_saved"], 1)

    def test_dedup_by_uid_and_text_hash(self):
        url = "https://sudact.ru/regular/doc/v1/"
        docs = {url: _verdict_doc(url, VERDICT_TEXT)}
        fetcher, parser = _make({}, docs)
        self._crawl(fetcher, parser, [url])
        # the same verdict under another url is a duplicate
        url2 = "https://sudact.ru/regular/doc/v2/"
        docs2 = {url2: _verdict_doc(url2, VERDICT_TEXT)}
        fetcher2, parser2 = _make({}, docs2)
        report = self._crawl(fetcher2, parser2, [url2])
        self.assertEqual(report.verdicts, 0)
        self.assertEqual(report.duplicates, 1)

    def test_http_errors_and_robots(self):
        pages = {
            "https://sudact.ru/regular/doc/e1/": FetchResult("e1", 500, None, "http_500", 5),
            "https://sudact.ru/regular/doc/e2/": FetchResult("e2", 404, None, "http_404", 1),
            "https://sudact.ru/regular/doc/e3/": FetchResult("e3", 0, None, "robots_disallowed", 0),
        }
        fetcher, parser = _make(pages, {})
        report = self._crawl(fetcher, parser, pages.keys())
        self.assertEqual(report.failed, 2)
        self.assertEqual(report.robots_blocked, 1)
        # 404 is terminal: not retried on the next run, 500 is
        self.assertIn("https://sudact.ru/regular/doc/e2/", self.sink.done_urls)
        self.assertIn("https://sudact.ru/regular/doc/e1/", self.sink.failed)

    def test_limit_pages_and_resume(self):
        docs = {
            f"https://sudact.ru/regular/doc/v{i}/": _verdict_doc(
                f"https://sudact.ru/regular/doc/v{i}/",
                VERDICT_TEXT + str(i),
                uid=f"21RS00{i:02d}-01-2026-00000{i}-01",
            )
            for i in range(5)
        }
        fetcher, parser = _make({}, docs)
        report = self._crawl(fetcher, parser, docs.keys(), limit_pages=2)
        self.assertEqual(report.stop_reason, "limit_pages")
        self.assertEqual(report.pages, 2)
        # second run continues and does not refetch processed urls
        fetcher2, parser2 = _make({}, docs)
        report2 = self._crawl(fetcher2, parser2, docs.keys())
        self.assertEqual(report2.already_done, 2)
        self.assertEqual(report2.pages, 3)

    def test_stop_after_verdicts_total_counts_previous_runs(self):
        url = "https://sudact.ru/regular/doc/v1/"
        docs = {url: _verdict_doc(url, VERDICT_TEXT)}
        fetcher, parser = _make({}, docs)
        self._crawl(fetcher, parser, [url])
        urls = [f"https://sudact.ru/regular/doc/w{i}/" for i in range(4)]
        docs2 = {
            u: _verdict_doc(u, VERDICT_TEXT_2 + str(i), uid=f"22RS00{i:02d}-01-2026-00002{i}-01")
            for i, u in enumerate(urls)
        }
        fetcher2, parser2 = _make({}, docs2)
        report = self._crawl(fetcher2, parser2, urls, stop_after_verdicts=2)
        self.assertEqual(report.stop_reason, "stop_after_verdicts")
        # stopping is checked between waves: one in-flight wave can overshoot
        self.assertGreaterEqual(self.sink.stats["verdicts_saved"], 2)
        self.assertLessEqual(self.sink.stats["verdicts_saved"], 3)

    def test_raw_html_cached_for_kept_docs(self):
        url = "https://sudact.ru/regular/doc/v1/"
        body = b"<html>verdict page</html>"
        docs = {url: _verdict_doc(url, VERDICT_TEXT)}
        fetcher, parser = _make({url: FetchResult(url, 200, body, None, 1)}, docs)
        self._crawl(fetcher, parser, [url])
        raw = list((self.sink.raw_dir).glob("*.html"))
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0].read_bytes(), body)

    def test_state_round_trip(self):
        url = "https://sudact.ru/regular/doc/v1/"
        docs = {url: _verdict_doc(url, VERDICT_TEXT)}
        fetcher, parser = _make({}, docs)
        self._crawl(fetcher, parser, [url])
        self.sink.save_state()
        self.sink.close()  # release the process lock for the reloaded store
        reloaded = SudactDiskStore(Path(self.tmp.name))
        try:
            self.assertIn(url, reloaded.done_urls)
            self.assertEqual(reloaded.stats["verdicts_saved"], 1)
            record = reloaded.verdicts_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(record), 1)
        finally:
            reloaded.close()

    def test_second_process_on_the_same_directory_is_rejected(self):
        from src.infrastructure.sudact_store import CrawlDirectoryBusy

        with self.assertRaises(CrawlDirectoryBusy):
            SudactDiskStore(Path(self.tmp.name))


if __name__ == "__main__":
    unittest.main()
