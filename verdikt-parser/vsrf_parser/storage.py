"""Хранилище результатов: JSONL, SQLite и resume-состояние краулера."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

log = logging.getLogger("vsrf_parser.storage")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS acts (
    claim_id TEXT PRIMARY KEY,
    case_number TEXT,
    act_kind TEXT,
    instance TEXT,
    department TEXT,
    register_date TEXT,
    first_court TEXT,
    first_case_number TEXT,
    first_act_type TEXT,
    first_judge TEXT,
    final_act_type TEXT,
    final_date TEXT,
    final_judgement TEXT,
    final_reporter TEXT,
    pdf_id TEXT,
    articles TEXT,
    parsed_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_acts_pdf ON acts(pdf_id);
CREATE INDEX IF NOT EXISTS idx_acts_case ON acts(case_number);
"""


class JsonlStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ids: set[str] = set()
        if self.path.exists():
            with self.path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("claim_id"):
                        self._ids.add(rec["claim_id"])
        self._fh = self.path.open("a", encoding="utf-8")

    def has(self, claim_id: str) -> bool:
        return claim_id in self._ids

    def append(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()
        self._ids.add(record["claim_id"])

    def __len__(self) -> int:
        return len(self._ids)

    def close(self) -> None:
        self._fh.close()


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(SCHEMA_SQL)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def upsert(self, record: dict[str, Any]) -> None:
        parsed = record.pop("parsed", None) or {}
        articles = ", ".join(record.get("articles") or [])
        self._conn.execute(
            """
            INSERT INTO acts (
                claim_id, case_number, act_kind, instance, department, register_date,
                first_court, first_case_number, first_act_type, first_judge,
                final_act_type, final_date, final_judgement, final_reporter,
                pdf_id, articles, parsed_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(claim_id) DO UPDATE SET
                case_number=excluded.case_number,
                act_kind=excluded.act_kind,
                instance=excluded.instance,
                department=excluded.department,
                register_date=excluded.register_date,
                first_court=excluded.first_court,
                first_case_number=excluded.first_case_number,
                first_act_type=excluded.first_act_type,
                first_judge=excluded.first_judge,
                final_act_type=excluded.final_act_type,
                final_date=excluded.final_date,
                final_judgement=excluded.final_judgement,
                final_reporter=excluded.final_reporter,
                pdf_id=excluded.pdf_id,
                articles=excluded.articles,
                parsed_json=excluded.parsed_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                record.get("claim_id"),
                record.get("case_number"),
                (parsed or {}).get("act_kind") or record.get("final_act_type"),
                record.get("instance"),
                record.get("department"),
                record.get("register_date"),
                record.get("first_court"),
                record.get("first_case_number"),
                record.get("first_act_type"),
                record.get("first_judge"),
                record.get("final_act_type"),
                record.get("final_date"),
                record.get("final_judgement"),
                record.get("final_reporter"),
                record.get("pdf_id"),
                articles,
                json.dumps({**record, "parsed": parsed}, ensure_ascii=False),
            ),
        )

    def pdf_ids(self) -> set[str]:
        cur = self._conn.execute("SELECT pdf_id FROM acts WHERE pdf_id IS NOT NULL")
        return {row[0] for row in cur.fetchall()}

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()


class State:
    """Resume-состояние: прогресс страниц, скачанные PDF/тексты, buildId."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def add_to_set(self, key: str, value: str) -> None:
        bucket = self.data.setdefault(key, [])
        if value not in bucket:
            bucket.append(value)

    def set_members(self, key: str) -> set[str]:
        return set(self.data.get(key) or [])

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(self.path)
