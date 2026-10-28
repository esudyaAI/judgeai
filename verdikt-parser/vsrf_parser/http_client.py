"""HTTP-транспорт с жёсткой фиксацией TLS 1.2, retry и rate limiting."""

from __future__ import annotations

import json
import ssl
import threading
import time
from typing import Any

import requests
import urllib3
import urllib3.exceptions
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class TLS12Adapter(HTTPAdapter):
    """Адаптер, ограничивающий TLS сверху версией 1.2 (обход EOF-бага Nginx ВС РФ)."""

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **kwargs: Any
    ) -> Any:
        ctx = create_urllib3_context()
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        if not ctx.check_hostname:
            ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(connections, maxsize, block, **kwargs)


class TLS12InsecureAdapter(TLS12Adapter):
    """Вариант без проверки сертификата (флаг --insecure)."""

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **kwargs: Any
    ) -> Any:
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        kwargs["ssl_context"] = ctx
        return super(TLS12Adapter, self).init_poolmanager(
            connections, maxsize, block, **kwargs
        )


class BuildIdStale(RuntimeError):
    """buildId Next.js устарел — требуется перерезолвинг."""


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, min_interval)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._min_interval
        if delay > 0:
            time.sleep(delay)


class HttpClient:
    """Синхронный HTTP-клиент: TLS 1.2, экспоненциальные ретраи, троттлинг."""

    def __init__(
        self,
        delay: float = 0.8,
        timeout: float = 30.0,
        retries: int = 6,
        headers: dict[str, str] | None = None,
        pool_size: int = 8,
        verify: bool = True,
    ) -> None:
        self.timeout = timeout
        self._verify = verify
        self.session = requests.Session()
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            backoff_factor=0.7,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            raise_on_status=False,
        )
        adapter_cls = TLS12Adapter if verify else TLS12InsecureAdapter
        adapter = adapter_cls(
            max_retries=retry,
            pool_connections=pool_size,
            pool_maxsize=pool_size,
        )
        self.session.mount("https://", adapter)
        self.session.headers.update(DEFAULT_HEADERS)
        if headers:
            self.session.headers.update(headers)
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._limiter = RateLimiter(delay)
        self.requests_sent = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        self._limiter.wait()
        self.requests_sent += 1
        resp = self.session.get(
            url,
            headers=headers,
            timeout=self.timeout,
            verify=self._verify,
        )
        return resp

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        resp = self.get(url, headers=headers)
        if resp.status_code == 404:
            raise BuildIdStale(f"404 от Next.js data API: {url}")
        resp.raise_for_status()
        if not resp.content:
            raise requests.ConnectionError(f"Пустой ответ: {url}")
        return json.loads(resp.content.decode("utf-8", errors="replace"))

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        resp = self.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content.decode("utf-8", errors="replace")

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        resp = self.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

    def close(self) -> None:
        self.session.close()
