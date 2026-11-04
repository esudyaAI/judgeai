"""Owner-scoped report persistence. Source locks match the existing case mutation lock."""

from hashlib import sha256
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select

from src.db.models import Attachment, Chat, Message
from src.db.reports import CaseReport
from src.domain.extraction import input_hash
from src.domain.reports import ReportNotFound, ReportUnavailable, StoredReport, freeze_snapshot
from src.infrastructure.report_materials import upload_digest
from src.schemas.analysis import CaseAnalysis

SUMMARY_FIELDS = (
    "id",
    "chat_id",
    "source_message_id",
    "version",
    "snapshot_sha256",
    "docx_sha256",
    "created_at",
)


def _stored(row: CaseReport) -> StoredReport:
    return StoredReport(
        str(row.id),
        row.owner_id,
        row.chat_id,
        row.source_message_id,
        row.version,
        row.snapshot,
        row.snapshot_sha256,
        bytes(row.docx_data),
        row.docx_sha256,
        row.created_at,
    )


class SqlReportRepository:
    def __init__(self, db):
        self.db = db

    async def source(self, user_id: int, chat_id: int, message_id: int) -> dict:
        chat = await self.db.scalar(
            select(Chat).where(Chat.id == chat_id, Chat.owner_id == user_id).with_for_update()
        )
        if chat is None:
            raise ReportNotFound("Дело не найдено")
        busy = await self.db.scalar(
            select(Message.id)
            .where(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.status.in_(("pending", "running")),
            )
            .limit(1)
        )
        if busy is not None:
            raise ReportUnavailable("Дождитесь завершения текущего анализа")
        message = await self.db.scalar(
            select(Message).where(
                Message.id == message_id, Message.chat_id == chat_id, Message.role == "assistant"
            )
        )
        if message is None:
            raise ReportNotFound("Результат не найден")
        if (
            message.status != "completed"
            or not isinstance(message.analysis, dict)
            or message.analysis.get("schema_version") != 1
        ):
            raise ReportUnavailable("Нет завершённого совместимого результата для отчёта")
        try:
            analysis = CaseAnalysis.model_validate(message.analysis)
        except ValidationError:
            raise ReportUnavailable("Результат несовместим с форматом отчёта") from None
        if not any(
            (
                analysis.fabula.strip(),
                analysis.legal_checks,
                analysis.defendants,
                analysis.imposed_sentence,
                analysis.qualification,
            )
        ):
            raise ReportUnavailable("В результате нет данных для отчёта")
        requested = analysis.extraction.documents if analysis.extraction else []
        if requested:
            ids = [entry.attachment_id for entry in requested if entry.attachment_id is not None]
            query = (
                select(Attachment)
                .join(Message)
                .where(Attachment.id.in_(ids), Message.chat_id == chat_id)
            )
        elif message.request_message_id is not None:
            query = (
                select(Attachment)
                .join(Message)
                .where(
                    Message.id == message.request_message_id,
                    Message.chat_id == chat_id,
                    Message.role == "user",
                )
            )
        else:
            query = select(Attachment).where(Attachment.id == -1)
        attachments = list(await self.db.scalars(query.order_by(Attachment.id)))
        materials, limitations = [], []
        expected = {
            entry.attachment_id: entry for entry in requested if entry.attachment_id is not None
        }
        if analysis.stats.documents and not requested:
            limitations.append(
                "В старом результате нет хешей материалов на момент анализа; "
                "доступный текст зафиксирован при создании отчёта."
            )
        if analysis.stats.documents and not attachments:
            limitations.append("Исходные материалы этого анализа недоступны или не установлены.")
        if len(attachments) < len(requested):
            limitations.append("Часть материалов исходного анализа недоступна.")
        for attachment in attachments:
            text = attachment.extracted_text or ""
            text_digest = input_hash(text)
            reference = expected.get(attachment.id)
            if reference is not None and reference.document_hash != text_digest:
                raise ReportUnavailable(
                    "Материалы изменились после анализа. Выполните новый анализ."
                )
            captured_digest = reference.original_sha256 if reference is not None else None
            current_digest = await upload_digest(attachment.stored_path)
            if captured_digest and current_digest and captured_digest != current_digest:
                raise ReportUnavailable("Оригинал изменился после анализа. Выполните новый анализ.")
            original_digest = captured_digest or current_digest
            if current_digest is None:
                limitations.append(
                    f"Оригинал «{attachment.filename}» недоступен для проверки хеша."
                )
            materials.append(
                {
                    "attachment_id": attachment.id,
                    "filename": attachment.filename,
                    "text": text,
                    "text_sha256": text_digest,
                    "original_sha256": original_digest,
                    "hash_captured_at": "analysis" if captured_digest else "report_creation",
                    "extraction_status": attachment.extraction_status,
                    "page_count": attachment.page_count,
                }
            )
        if not message.analysis.get("provenance"):
            limitations.append(
                "Версии модели, промпта и редакций норм в источнике не зафиксированы; "
                "они неизвестны."
            )
        limitations.extend((message.analysis.get("provenance") or {}).get("limitations", []))
        return {
            "schema_version": 1,
            "source_message_id": message.id,
            "chat_title": chat.title,
            "analysis": message.analysis,
            "materials": materials,
            "limitations": limitations,
            "human_review": message.analysis.get("human_review") or {"status": "not_reviewed"},
        }

    async def existing(self, user_id: int, chat_id: int, digest: str):
        row = await self.db.scalar(
            select(CaseReport).where(
                CaseReport.owner_id == user_id,
                CaseReport.chat_id == chat_id,
                CaseReport.snapshot_sha256 == digest,
            )
        )
        return _stored(row) if row else None

    async def next_version(self, chat_id: int) -> int:
        return (
            await self.db.scalar(
                select(func.max(CaseReport.version)).where(CaseReport.chat_id == chat_id)
            )
            or 0
        ) + 1

    async def save(
        self,
        user_id,
        chat_id,
        message_id,
        version,
        snapshot,
        digest,
        artifact,
        artifact_digest,
        created_at,
    ):
        row = CaseReport(
            owner_id=user_id,
            chat_id=chat_id,
            source_message_id=message_id,
            version=version,
            snapshot=snapshot,
            snapshot_sha256=digest,
            docx_data=artifact,
            docx_sha256=artifact_digest,
            created_at=created_at,
        )
        self.db.add(row)
        await self.db.flush()
        return _stored(row)

    async def get(self, user_id: int, report_id: UUID) -> StoredReport:
        row = await self.db.scalar(
            select(CaseReport)
            .join(Chat)
            .where(
                CaseReport.id == report_id, CaseReport.owner_id == user_id, Chat.owner_id == user_id
            )
        )
        if row is None:
            raise ReportNotFound("Отчёт не найден")
        if (
            freeze_snapshot(row.snapshot)[1] != row.snapshot_sha256
            or sha256(row.docx_data).hexdigest() != row.docx_sha256
        ):
            raise ReportUnavailable("Нарушена целостность сохранённого отчёта")
        return _stored(row)

    async def list(self, user_id: int, chat_id: int | None, limit: int, offset: int):
        query = (
            select(*(getattr(CaseReport, field) for field in SUMMARY_FIELDS))
            .join(Chat)
            .where(CaseReport.owner_id == user_id, Chat.owner_id == user_id)
        )
        if chat_id is not None:
            query = query.where(CaseReport.chat_id == chat_id)
        rows = (
            await self.db.execute(
                query.order_by(CaseReport.created_at.desc(), CaseReport.version.desc())
                .limit(limit)
                .offset(offset)
            )
        ).mappings()
        return [{**row, "id": str(row["id"])} for row in rows]
