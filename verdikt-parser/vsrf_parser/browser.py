"""Browser-транспорт на nodriver: fallback, когда прямой HTTP заблокирован."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time
from typing import Any

from .http_client import BuildIdStale

log = logging.getLogger("vsrf_parser.browser")

FETCH_TEXT_JS = """
fetch(url, {headers: Object.assign({}, extra_headers)})
    .then(r => r.text())
"""
FETCH_B64_JS = """
(async () => {
    const r = await fetch(url, {headers: Object.assign({}, extra_headers)});
    const b = new Uint8Array(await r.arrayBuffer());
    let s = '';
    const CH = 0x8000;
    for (let i = 0; i < b.length; i += CH) {
        s += String.fromCharCode.apply(null, b.subarray(i, i + CH));
    }
    return btoa(s);
})()
"""


class BrowserTransport:
    """Синхронный транспорт поверх nodriver (Chrome), совместим с VSRFClient."""

    def __init__(self, delay: float = 1.5, headless: bool = False) -> None:
        self._delay = delay
        self._headless = headless
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._browser: Any = None
        self._tab: Any = None
        self._ready = threading.Event()
        self._next_allowed = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._next_allowed - now
        self._next_allowed = max(now, self._next_allowed) + self._delay
        if wait > 0:
            time.sleep(wait)

    def start(self) -> None:
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="nodriver-loop", daemon=True
        )
        self._thread.start()
        self._submit(self._start_browser())
        if not self._ready.wait(timeout=60):
            raise RuntimeError("Не удалось запустить браузер (nodriver) в течение 60 c")

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro: Any) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _start_browser(self) -> None:
        import nodriver as uc

        self._browser = await uc.start(headless=self._headless)
        self._tab = await self._browser.get("https://www.vsrf.ru/lk/practice/acts")
        await self._tab.sleep(1)
        self._ready.set()
        log.info("nodriver: браузер запущен, вкладка vsrf.ru открыта")

    def _headers_for(self, url: str) -> dict[str, str]:
        headers = {"Referer": "https://www.vsrf.ru/lk/practice/acts"}
        if "_next/data" in url:
            headers["x-nextjs-data"] = "1"
        return headers

    async def _fetch_text(self, url: str) -> str:
        assert self._tab is not None
        args = json.dumps({"url": url, "extra_headers": self._headers_for(url)})
        js = (
            "async (args) => { const {url, extra_headers} = args; "
            "const r = await fetch(url, {headers: extra_headers}); "
            "return await r.text(); }"
        )
        try:
            result = await self._tab.evaluate(
                f"({js})({args})", await_promise=True, return_by_value=True
            )
        except Exception:
            raise
        if isinstance(result, tuple):
            result = result[0]
        return str(result)

    async def _fetch_b64(self, url: str) -> str:
        assert self._tab is not None
        args = json.dumps({"url": url, "extra_headers": self._headers_for(url)})
        js = (
            "async (args) => { const {url, extra_headers} = args; "
            "const r = await fetch(url, {headers: extra_headers}); "
            "const b = new Uint8Array(await r.arrayBuffer()); "
            "let s = ''; const CH = 0x8000; "
            "for (let i = 0; i < b.length; i += CH) "
            "s += String.fromCharCode.apply(null, b.subarray(i, i + CH)); "
            "return btoa(s); }"
        )
        result = await self._tab.evaluate(
            f"({js})({args})", await_promise=True, return_by_value=True
        )
        if isinstance(result, tuple):
            result = result[0]
        return str(result)

    async def _navigate(self, url: str) -> str:
        assert self._browser is not None
        tab = await self._browser.get(url)
        await tab.sleep(0.5)
        return await tab.get_content()

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        self.start()
        self._throttle()
        if "_next/data" in url or url.endswith(".json"):
            try:
                return self._submit(self._fetch_text(url))
            except Exception as exc:
                log.warning("browser fetch(text) %s: %s — навигация напрямую", url, exc)
        return self._submit(self._navigate(url))

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        text = self.get_text(url, headers=headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            if '"notFound"' in text or "404" in text[:200]:
                raise BuildIdStale(f"404/не JSON от {url}") from exc
            raise

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        self.start()
        self._throttle()
        b64 = self._submit(self._fetch_b64(url))
        return base64.b64decode(b64)

    def close(self) -> None:
        if self._loop is None:
            return
        async def _stop() -> None:
            if self._browser is not None:
                self._browser.stop()
        try:
            self._submit(_stop())
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=10)
        self._loop = None
