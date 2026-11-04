"""Private immutable report values; never recalculate a saved report on retrieval."""

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


class ReportNotFound(LookupError):
    pass


class ReportUnavailable(ValueError):
    pass


class ReportExportFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredReport:
    id: str
    owner_id: int
    chat_id: int
    source_message_id: int
    version: int
    snapshot: dict
    snapshot_sha256: str
    docx_data: bytes
    docx_sha256: str
    created_at: datetime


def freeze_snapshot(value: dict) -> tuple[dict, str]:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return json.loads(raw), sha256(raw.encode()).hexdigest()
