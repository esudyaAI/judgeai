"""Клиент Next.js Data API портала ВС РФ (vsrf.ru/lk/practice)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

from .http_client import BuildIdStale, HttpClient
from .listing import parse_listing
from .models import ActListItem, ClaimDetails

log = logging.getLogger("vsrf_parser.client")

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


class Transport(Protocol):
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any: ...
    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str: ...
    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes: ...


class ItemsPage:
    def __init__(
        self,
        page: int,
        total: int | None,
        last: bool | None,
        items: list[ActListItem],
    ) -> None:
        self.page = page
        self.total = total
        self.last = last
        self.items = items


class VSRFClient:
    BASE_URL = "https://www.vsrf.ru"
    ACTS_PATH = "/lk/practice/acts"
    DATA_PREFIX = "/lk/practice/_next/data/{build_id}"
    DATA_HEADERS = {"x-nextjs-data": "1", "Referer": "https://www.vsrf.ru/lk/practice/acts"}
    CASE_TYPES = ("CRIMINAL", "CIVIL", "ADMINISTRATIVE", "ECONOMIC")
    INSTANCES = (
        "FIRST",
        "APPEAL",
        "CASSATION_NOT_IN_TO_FORCE",
        "CASSATION_INTO_FORCE",
        "SUPERVISORY",
    )

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._build_id: str | None = None
        self._build_id_at: float = 0.0

    @property
    def build_id(self) -> str | None:
        return self._build_id

    def resolve_build_id(self, force: bool = False) -> str:
        """Извлекает актуальный buildId из __NEXT_DATA__ страницы реестра."""
        if (
            not force
            and self._build_id
            and time.time() - self._build_id_at < 86400
        ):
            return self._build_id
        url = f"{self.BASE_URL}{self.ACTS_PATH}"
        html = self.transport.get_text(url)
        m = NEXT_DATA_RE.search(html)
        if not m:
            raise RuntimeError("__NEXT_DATA__ не найден на странице /lk/practice/acts")
        data = json.loads(m.group(1))
        build_id = data.get("buildId")
        if not build_id:
            raise RuntimeError("buildId отсутствует в __NEXT_DATA__")
        self._build_id = build_id
        self._build_id_at = time.time()
        log.info("Актуальный Next.js buildId: %s", build_id)
        return build_id

    def _data_url(self, path: str) -> str:
        build_id = self._build_id or self.resolve_build_id()
        return f"{self.BASE_URL}{self.DATA_PREFIX.format(build_id=build_id)}{path}"

    def fetch_acts_page(
        self,
        page: int = 1,
        case_type: str = "CRIMINAL",
        instance: str | None = None,
        text_query: str | None = None,
        act_type_id: int | None = None,
    ) -> ItemsPage:
        """Загружает страницу реестра и разбирает карточки дел."""
        params: dict[str, Any] = {"caseType": case_type, "page": page}
        if instance:
            params["instance"] = instance
        if text_query:
            params["text"] = text_query
        if act_type_id is not None:
            params["actType"] = act_type_id
        query = "&".join(
            f"{k}={v}" for k, v in params.items()
        )
        url = f"{self._data_url('/acts.json')}?{query}"
        try:
            payload = self.transport.get_json(url, headers=self.DATA_HEADERS)
        except BuildIdStale:
            log.warning("buildId устарел, перерезолвинг и повтор запроса")
            self.resolve_build_id(force=True)
            url = f"{self._data_url('/acts.json')}?{query}"
            payload = self.transport.get_json(url, headers=self.DATA_HEADERS)
        items_data = payload.get("pageProps", {}).get("initialItemsData", {})
        items = parse_listing(items_data.get("content", ""))
        return ItemsPage(
            page=page,
            total=items_data.get("totalElements"),
            last=items_data.get("last"),
            items=items,
        )

    def fetch_claim(self, claim_id: str) -> ClaimDetails:
        """Загружает детальную карточку производства по claim_id."""
        url = f"{self._data_url(f'/claims/{claim_id}.json')}"
        try:
            payload = self.transport.get_json(url, headers=self.DATA_HEADERS)
        except BuildIdStale:
            self.resolve_build_id(force=True)
            url = f"{self._data_url(f'/claims/{claim_id}.json')}"
            payload = self.transport.get_json(url, headers=self.DATA_HEADERS)
        claims = payload.get("pageProps", {}).get("claims", [])
        main = _pick_main_claim(claims)
        if main is None:
            raise ValueError(f"Пустой ответ по делу {claim_id}")
        return ClaimDetails.from_api(claim_id, main)

    def pdf_url(self, stor_id: str) -> str:
        return f"{self.BASE_URL}/lk/practice/stor_pdf/{stor_id}"

    def fetch_pdf(self, stor_id: str) -> bytes:
        data = self.transport.get_bytes(self.pdf_url(stor_id))
        if not data.startswith(b"%PDF"):
            head = data[:200]
            raise ValueError(
                f"Ответ по stor_pdf/{stor_id} не является PDF: {head!r}"
            )
        return data

    def fetch_pdf_by_url(self, url: str) -> bytes:
        if not url.startswith("http"):
            url = f"{self.BASE_URL}{url}"
        data = self.transport.get_bytes(url)
        if not data.startswith(b"%PDF"):
            raise ValueError(f"Ответ по {url} не является PDF")
        return data


def _pick_main_claim(claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not claims:
        return None
    for claim in claims:
        if claim.get("claimType") == "CASE":
            return claim
    for claim in claims:
        if (claim.get("finalAct") or {}).get("downloadLink"):
            return claim
    return claims[0]


def make_default_client(
    delay: float = 0.8, timeout: float = 30.0, retries: int = 6
) -> tuple[VSRFClient, HttpClient]:
    http = HttpClient(delay=delay, timeout=timeout, retries=retries)
    return VSRFClient(http), http
