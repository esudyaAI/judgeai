"""Persist complete versions under the same case lock as send/recalculate/delete."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from src.db.analysis_revisions import AnalysisRevision
from src.db.models import Chat, Message
from src.domain.analysis_revisions import RevisionIntegrityError, RevisionNotFound
from src.domain.reports import freeze_snapshot


class SqlAnalysisRevisionStore:
    def __init__(self, db):
        self.db = db

    async def owned_source(self, owner_id, chat_id, message_id, *, lock=False):
        query = select(Chat).where(Chat.id == chat_id, Chat.owner_id == owner_id)
        if lock:
            query = query.with_for_update()
        if await self.db.scalar(query) is None:
            raise RevisionNotFound
        message = await self.db.scalar(
            select(Message).where(
                Message.id == message_id, Message.chat_id == chat_id, Message.role == "assistant"
            )
        )
        if message is None:
            raise RevisionNotFound
        return message

    async def append(
        self,
        owner_id,
        chat_id,
        message_id,
        result,
        inputs,
        *,
        kind="machine",
        client_request_id=None,
        payload_sha256=None,
    ):
        await self.owned_source(owner_id, chat_id, message_id, lock=True)
        latest = (
            await self.db.execute(
                select(AnalysisRevision.id, AnalysisRevision.version)
                .where(
                    AnalysisRevision.source_message_id == message_id,
                    AnalysisRevision.owner_id == owner_id,
                )
                .order_by(AnalysisRevision.version.desc())
                .limit(1)
            )
        ).first()
        version = latest.version + 1 if latest is not None else 1
        revision_id = uuid4()
        review = result.get("human_review") or {
            "status": "unknown" if kind == "legacy" else "not_reviewed"
        }
        output, result_hash = freeze_snapshot(
            {
                **result,
                "human_review": review,
                "revision": {
                    "id": str(revision_id),
                    "version": version,
                    "kind": kind,
                    "base_revision_id": str(latest.id) if latest else None,
                },
            }
        )
        frozen, inputs_hash = freeze_snapshot(inputs) if inputs is not None else (None, None)
        row = AnalysisRevision(
            id=revision_id,
            owner_id=owner_id,
            chat_id=chat_id,
            source_message_id=message_id,
            version=version,
            base_revision_id=latest.id if latest else None,
            kind=kind,
            client_request_id=client_request_id,
            payload_sha256=payload_sha256,
            calculation_inputs=frozen,
            inputs_sha256=inputs_hash,
            result=output,
            result_sha256=result_hash,
            review=review,
            created_at=datetime.now(UTC),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def archive_current(self, owner_id, chat_id, message_id):
        message = await self.owned_source(owner_id, chat_id, message_id, lock=True)
        if not isinstance(message.analysis, dict):
            return None
        # Only a genuinely stored and matching revision is already archived.
        digest = freeze_snapshot(message.analysis)[1]
        existing = await self.db.scalar(
            select(AnalysisRevision)
            .where(
                AnalysisRevision.owner_id == owner_id,
                AnalysisRevision.source_message_id == message_id,
                AnalysisRevision.result_sha256 == digest,
            )
            .limit(1)
        )
        if existing is not None and existing.result == message.analysis:
            return existing
        return await self.append(
            owner_id, chat_id, message_id, message.analysis, None, kind="legacy"
        )

    async def list(self, owner_id, chat_id, message_id, limit=50, offset=0):
        await self.owned_source(owner_id, chat_id, message_id)
        fields = (
            "id",
            "chat_id",
            "source_message_id",
            "version",
            "base_revision_id",
            "kind",
            "inputs_sha256",
            "result_sha256",
            "created_at",
        )
        query = (
            select(*(getattr(AnalysisRevision, field) for field in fields))
            .where(
                AnalysisRevision.owner_id == owner_id,
                AnalysisRevision.source_message_id == message_id,
            )
            .order_by(AnalysisRevision.version.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.db.execute(query)).mappings().all()

    async def get(self, owner_id, chat_id, message_id, revision_id: UUID):
        await self.owned_source(owner_id, chat_id, message_id)
        row = await self.db.scalar(
            select(AnalysisRevision).where(
                AnalysisRevision.id == revision_id,
                AnalysisRevision.owner_id == owner_id,
                AnalysisRevision.chat_id == chat_id,
                AnalysisRevision.source_message_id == message_id,
            )
        )
        if row is None:
            raise RevisionNotFound
        if (
            row.review != row.result.get("human_review")
            or ((row.calculation_inputs is None) != (row.inputs_sha256 is None))
            or freeze_snapshot(row.result)[1] != row.result_sha256
            or (
                row.calculation_inputs is not None
                and freeze_snapshot(row.calculation_inputs)[1] != row.inputs_sha256
            )
        ):
            raise RevisionIntegrityError
        return row
