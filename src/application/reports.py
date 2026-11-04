"""Snapshot a completed result through owner-scoped persistence and an export port."""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from src.domain.reports import ReportExportFailed, StoredReport, freeze_snapshot


class ReportRepository(Protocol):
    async def source(self, user_id: int, chat_id: int, message_id: int) -> dict: ...
    async def existing(self, user_id: int, chat_id: int, digest: str) -> StoredReport | None: ...
    async def next_version(self, chat_id: int) -> int: ...
    async def save(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        version: int,
        snapshot: dict,
        digest: str,
        artifact: bytes,
        artifact_digest: str,
        created_at: datetime,
    ) -> StoredReport: ...


class ReportExporter(Protocol):
    async def render(self, snapshot: dict, version: int, created_at: datetime) -> bytes: ...


class CreateReport:
    def __init__(self, repository: ReportRepository, exporter: ReportExporter):
        self.repository, self.exporter = repository, exporter

    async def execute(
        self, user_id: int, chat_id: int, message_id: int
    ) -> tuple[StoredReport, bool]:
        snapshot, digest = freeze_snapshot(
            await self.repository.source(user_id, chat_id, message_id)
        )
        existing = await self.repository.existing(user_id, chat_id, digest)
        if existing:
            return existing, False
        version = await self.repository.next_version(chat_id)
        created_at = datetime.now(UTC)
        try:
            artifact = await self.exporter.render(snapshot, version, created_at)
            if not isinstance(artifact, bytes) or not artifact.startswith(b"PK"):
                raise ValueError("invalid artifact")
        except Exception:
            raise ReportExportFailed("Не удалось сформировать DOCX. Повторите попытку.") from None
        report = await self.repository.save(
            user_id,
            chat_id,
            message_id,
            version,
            snapshot,
            digest,
            artifact,
            sha256(artifact).hexdigest(),
            created_at,
        )
        return report, True
