"""Оркестратор пайплайна: листинг -> карточки -> PDF -> текст -> разбор."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from .client import VSRFClient
from .http_client import RateLimiter
from .models import ActListItem
from .pdf import download_pdf, extract_text, save_text
from .storage import JsonlStore, SqliteStore, State
from .text_parser import parse_act_text

log = logging.getLogger("vsrf_parser.crawler")

ProgressCallback = Callable[[str], None]


class Crawler:
    def __init__(
        self,
        client: VSRFClient,
        out_dir: Path,
        case_type: str = "CRIMINAL",
        instance: str | None = None,
        workers: int = 1,
    ) -> None:
        self.client = client
        self.out_dir = out_dir
        self.pdf_dir = out_dir / "pdfs"
        self.text_dir = out_dir / "texts"
        self.case_type = case_type
        self.instance = instance
        self.workers = max(1, workers)
        self.state = State(out_dir / "state.json")
        self.jsonl: JsonlStore | None = None
        self.sqlite: SqliteStore | None = None

    def open_stores(self, sqlite: bool = False) -> None:
        self.jsonl = JsonlStore(self.out_dir / "metadata.jsonl")
        if sqlite:
            self.sqlite = SqliteStore(self.out_dir / "acts.db")

    def close(self) -> None:
        if self.jsonl:
            self.jsonl.close()
        if self.sqlite:
            self.sqlite.close()

    def total_acts(self) -> int | None:
        page = self.client.fetch_acts_page(
            page=1, case_type=self.case_type, instance=self.instance
        )
        return page.total

    def iter_act_pages(
        self,
        start_page: int = 1,
        max_pages: int | None = None,
    ):
        """Итерация по страницам реестра с авто-определением конца."""
        first = self.client.fetch_acts_page(
            page=start_page, case_type=self.case_type, instance=self.instance
        )
        total = first.total or 0
        last_page = (total + 19) // 20 if total else start_page
        if max_pages is not None:
            last_page = min(last_page, start_page + max_pages - 1)
        log.info(
            "Реестр: %d дел, ~%d страниц (тип=%s, инстанция=%s)",
            total, max(1, (total + 19) // 20), self.case_type, self.instance or "любая",
        )
        yield first
        for page in range(start_page + 1, last_page + 1):
            yield self.client.fetch_acts_page(
                page=page, case_type=self.case_type, instance=self.instance
            )

    def collect_claims(
        self,
        items: list[ActListItem],
        max_claims: int | None = None,
        fetch_details: bool = True,
    ) -> int:
        """Дозагружает карточки дел и пишет их в хранилище. Возвращает число новых."""
        assert self.jsonl is not None
        todo = [item for item in items if not self.jsonl.has(item.claim_id)]
        if max_claims is not None:
            todo = todo[:max_claims]
        if not todo:
            return 0
        if not fetch_details:
            for item in todo:
                self.jsonl.append(item.as_dict())
            return len(todo)
        new_count = 0

        def fetch_record(item: ActListItem) -> dict:
            details = self.client.fetch_claim(item.claim_id)
            return details.to_record()

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(fetch_record, item): item for item in todo}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    log.warning(
                        "Не удалось получить карточку %s: %s", item.claim_id, exc
                    )
                    continue
                self.jsonl.append(record)
                if self.sqlite:
                    self.sqlite.upsert(dict(record))
                new_count += 1
                if new_count % 100 == 0:
                    log.info(
                        "Обработано карточек: %d (последнее: %s)",
                        new_count, item.claim_id,
                    )
        return new_count

    def collect_pdf_ids(self) -> list[str]:
        """Собирает pdf_id из JSONL-метаданных."""
        records = self.load_records()
        ids: list[str] = []
        seen: set[str] = set()
        for rec in records:
            pdf_id = rec.get("pdf_id")
            if pdf_id and pdf_id not in seen:
                seen.add(pdf_id)
                ids.append(pdf_id)
        return ids

    def load_records(self) -> list[dict]:
        records: list[dict] = []
        path = self.out_dir / "metadata.jsonl"
        if not path.exists():
            return records

        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def download_pdfs(
        self, pdf_ids: list[str], limit: int | None = None, pdf_delay: float = 1.0
    ) -> int:
        downloaded = 0
        done = self.state.set_members("pdfs_done")
        todo = [pid for pid in pdf_ids if pid not in done]
        if limit is not None:
            todo = todo[:limit]
        if not todo:
            return 0
        limiter = RateLimiter(max(pdf_delay, 0.0))

        def fetch_pdf(pdf_id: str) -> str:
            dest = self.pdf_dir / f"{pdf_id}.pdf"
            limiter.wait()
            try:
                return download_pdf(self.client, pdf_id, dest)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status != 429:
                    raise
                log.warning(
                    "429 (throttle) на PDF %s: пауза 60с и повтор", pdf_id
                )
                time.sleep(60)
                limiter.wait()
                return download_pdf(self.client, pdf_id, dest)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(fetch_pdf, pid): pid for pid in todo}
            for future in as_completed(futures):
                pdf_id = futures[future]
                try:
                    status = future.result()
                except Exception as exc:
                    log.warning("PDF %s не скачан: %s", pdf_id, exc)
                    continue
                if status == "downloaded":
                    downloaded += 1
                    if downloaded % 100 == 0:
                        log.info("Скачано PDF: %d", downloaded)
                self.state.add_to_set("pdfs_done", pdf_id)
        self.state.save()
        return downloaded

    def extract_texts(self, ocr: bool = True, limit: int | None = None) -> int:
        extracted = 0
        done = self.state.set_members("texts_done")
        todo = [
            p for p in sorted(self.pdf_dir.glob("*.pdf")) if p.stem not in done
        ]
        if limit is not None:
            todo = todo[:limit]
        if not todo:
            return 0

        def run_extract(pdf_path: Path):
            return pdf_path, extract_text(pdf_path, ocr=ocr)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(run_extract, p) for p in todo]
            for future in as_completed(futures):
                try:
                    pdf_path, result = future.result()
                except Exception as exc:
                    log.warning("Текст не извлечён: %s", exc)
                    continue
                save_text(self.text_dir / f"{pdf_path.stem}.txt", result.text)
                meta_path = self.text_dir / f"{pdf_path.stem}.meta.json"
                meta_path.write_text(
                    json.dumps(
                        {
                            "has_text_layer": result.has_text_layer,
                            "ocr_used": result.ocr_used,
                            "pages": result.pages,
                            "needs_ocr": result.needs_ocr,
                        }
                    ),
                    encoding="utf-8",
                )
                if result.needs_ocr:
                    log.warning(
                        "%s: текстовый слой отсутствует, OCR недоступен "
                        "(установите tesseract + pytesseract)", pdf_path.name,
                    )
                extracted += 1
                self.state.add_to_set("texts_done", pdf_path.stem)
        self.state.save()
        return extracted

    def parse_texts(self, limit: int | None = None) -> int:
        out_path = self.out_dir / "parsed.jsonl"
        parsed_done = self.state.set_members("parsed_done")
        count = 0
        with out_path.open("a", encoding="utf-8") as fh:

            for text_path in sorted(self.text_dir.glob("*.txt")):
                if limit is not None and count >= limit:
                    break
                if text_path.stem in parsed_done:
                    continue
                text = text_path.read_text(encoding="utf-8", errors="replace")
                parsed = parse_act_text(text, source_path=str(text_path))
                record = parsed.to_record()
                record["pdf_id"] = text_path.stem
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
                self.state.add_to_set("parsed_done", text_path.stem)
        self.state.save()
        return count
