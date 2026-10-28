"""Резервный источник: агрегатор СудАкт (sudact.ru/vsrf) c polling-поиском."""

from __future__ import annotations

import logging
import re
import time
from html import unescape
from typing import Any
from urllib.parse import quote

import requests
from lxml import html as lxml_html

log = logging.getLogger("vsrf_parser.sudact")

BASE = "https://sudact.ru"
SEARCH_URL = f"{BASE}/vsrf/doc_ajax/"
DOC_HREF_RE = re.compile(r'href="(/vsrf/doc/[^"]+)"')
MAX_POLLS = 40
POLL_DELAY = 2.0


class SudActClient:
    def __init__(self, delay: float = 1.5, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 "
                    "Firefox/128.0"
                ),
                "Accept": "*/*",
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Referer": f"{BASE}/vsrf/",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _get(self, url: str, **kw: Any) -> requests.Response:
        time.sleep(self.delay)
        resp = self.session.get(url, timeout=self.timeout, **kw)
        resp.raise_for_status()
        return resp

    def search(
        self,
        query: str,
        case_doc: str = "",
        law_chunk: str = "",
        max_polls: int = MAX_POLLS,
    ) -> dict[str, Any]:
        """Регистрирует поисковую задачу и опрашивает до статуса finished."""
        params = {
            "vsrf-txt": query,
            "vsrf-case_doc": case_doc,
            "vsrf-lawchunkinfo": law_chunk,
        }
        qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
        url = f"{SEARCH_URL}?{qs}"
        payload: dict[str, Any] = {}
        for attempt in range(max_polls):
            resp = self._get(url)
            payload = resp.json()
            status = payload.get("search_status")
            if status == "finished":
                content = payload.get("content", "")
                if "<li" in content or "/vsrf/doc/" in content or not content:
                    return payload
                time.sleep(1.5)
                resp = self._get(url)
                return resp.json()
            log.debug("sudact poll %d: %s", attempt + 1, status)
            time.sleep(POLL_DELAY)
        raise TimeoutError(
            f"sudact не завершил поиск за {max_polls} опросов (последний статус: "
            f"{payload.get('search_status')})"
        )

    @staticmethod
    def parse_search_results(payload: dict[str, Any]) -> list[dict[str, str]]:
        """Разбирает content ответа на список документов (два варианта разметки)."""
        content = payload.get("content", "")
        results: list[dict[str, str]] = []
        if not content.strip():
            return results
        root = lxml_html.fromstring(f"<div>{content}</div>")
        seen: set[str] = set()
        for li in root.iter("li"):
            slug: str | None = None
            for div in li.iter("div"):
                m = re.match(r"bookmark_doc_([\w-]+)$", div.get("id") or "")
                if m:
                    slug = m.group(1)
                    break
            title = ""
            for a in li.iter("a"):
                href = a.get("href") or ""
                hm = re.match(r"/vsrf/doc/([\w-]+)/", href)
                if hm and slug is None:
                    slug = hm.group(1)
                text = unescape(re.sub(r"<[^>]+>", " ", a.text_content() or ""))
                text = re.sub(r"\s+", " ", text).strip()
                if text and not title:
                    title = text
            if slug and slug not in seen:
                seen.add(slug)
                results.append(
                    {"slug": slug, "url": f"{BASE}/vsrf/doc/{slug}/", "title": title}
                )
        if not results:
            for m in DOC_HREF_RE.finditer(content):
                href = m.group(1)
                hm = re.match(r"/vsrf/doc/([\w-]+)/", href)
                if hm and hm.group(1) not in seen:
                    seen.add(hm.group(1))
                    results.append(
                        {
                            "slug": hm.group(1),
                            "url": f"{BASE}/vsrf/doc/{hm.group(1)}/",
                            "title": "",
                        }
                    )
        return results

    def fetch_document_text(self, doc_url: str) -> str:
        """Загружает страницу документа и извлекает текст акта."""
        resp = self._get(doc_url)
        resp.headers.pop("Content-Encoding", None)
        html_text = resp.content.decode("utf-8", errors="replace")
        root = lxml_html.fromstring(html_text)
        candidates = root.xpath('//td[contains(@class,"h-col1")]')
        if not candidates:
            candidates = root.xpath('//div[contains(@class,"h-content")]')
        best: str | None = None
        for node in candidates:
            text = (node.text_content() or "").strip()
            if best is None or len(text) > len(best):
                best = text
        if best is None:
            for node in root.xpath("//body"):
                best = (node.text_content() or "").strip()
        return re.sub(r"\n{3,}", "\n\n", best or "")

    def search_and_fetch(
        self, query: str, fetch_docs: int = 3, **kw: Any
    ) -> dict[str, Any]:
        payload = self.search(query, **kw)
        results = self.parse_search_results(payload)
        docs = []
        for item in results[:fetch_docs]:
            try:
                text = self.fetch_document_text(item["url"])
            except Exception as exc:
                log.warning("sudact: не получен документ %s: %s", item["url"], exc)
                text = ""
            docs.append({**item, "text": text})
        return {
            "total_found": payload.get("total_found", ""),
            "results": results,
            "documents": docs,
        }

    def close(self) -> None:
        self.session.close()
