"""Replay frozen inputs and persist a human version without providers or mutable corpora."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from src.application.fact_review import PreparedReview, ReviewBase
from src.db.analysis_revisions import AnalysisRevision
from src.db.models import Chat, Message
from src.domain.analysis_revisions import RevisionIntegrityError
from src.domain.fact_review import ReviewConflict
from src.domain.reports import freeze_snapshot
from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
from src.infrastructure.calculation_inputs import _json_value, load_inputs, replay_inputs
from src.infrastructure.frozen_practice import RESET_WARNING, refresh_frozen_practice
from src.infrastructure.review_sources import load_review_sources


class FrozenReviewCalculator:
    def prepare(self, inputs):
        try:
            snapshot = load_inputs(inputs)
            documents, context = load_review_sources(inputs)
            if any(
                p.sentence is not None
                and p.sentence.counts
                and (p.guilt_by_count is None or p.aggregate_absorption is None)
                for p in snapshot.kwargs.prepared_sentencing_inputs.values()
            ):
                raise ValueError("Saved per-count guilt is missing")
        except ValueError:
            raise ReviewConflict("unsupported_inputs") from None
        return PreparedReview(
            snapshot.kwargs.prepared_legal_inputs,
            snapshot.kwargs.prepared_sentencing_inputs,
            documents,
            context,
        )

    def calculate(self, inputs, legal, sentencing, changed):
        snapshot = load_inputs(inputs)
        prior_references = {
            index: tuple(c.reference for c in p.sentence.counts) if p.sentence else ()
            for index, p in snapshot.kwargs.prepared_sentencing_inputs.items()
        }
        current_references = {
            index: tuple(c.reference for c in p.sentence.counts) if p.sentence else ()
            for index, p in sentencing.items()
        }
        if prior_references != current_references:
            snapshot.facts.qualification = None
            snapshot.facts.sanction_max_months = None
            snapshot.kwargs.statute = None
            if (
                len(sentencing) == 1
                and sentencing[0].sentence is not None
                and len(sentencing[0].sentence.counts) == 1
            ):
                reference = sentencing[0].sentence.counts[0].reference
                snapshot.kwargs.statute = next(
                    (s.reading for s in snapshot.kwargs.count_statutes if s.reference == reference),
                    None,
                )
        snapshot.kwargs.prepared_legal_inputs = legal
        snapshot.kwargs.prepared_sentencing_inputs = sentencing
        if changed:
            # Invalidate before the async frozen-pool refresh; no old comparison
            # may leak if refreshed inputs are incomplete or the original bank is absent.
            snapshot.facts.variants = []
            snapshot.facts.recommended_months = None
            snapshot.facts.fabula = (
                "Факты скорректированы пользователем. Исходная машинная сводка "
                "сохранена в предыдущей версии."
            )
            snapshot.review_invalidations = ["practice"]
            warning = RESET_WARNING
            if warning not in snapshot.kwargs.extra_warnings:
                snapshot.kwargs.extra_warnings.append(warning)
        payload = json.loads(
            json.dumps(_json_value(snapshot.model_dump(mode="python")), allow_nan=False)
        )
        result = replay_inputs(payload).model_dump(mode="json", by_alias=True)
        return payload, result

    async def refresh_practice(self, payload, result):
        return await refresh_frozen_practice(payload, result)


class SqlFactReviewStore:
    def __init__(self, db):
        self.db = db
        self.revisions = SqlAnalysisRevisionStore(db)

    async def lock_source(self, owner_id, chat_id, message_id):
        await self.revisions.owned_source(owner_id, chat_id, message_id, lock=True)

    async def request(self, owner_id, request_id, digest):
        row = await self.db.scalar(
            select(AnalysisRevision).where(
                AnalysisRevision.owner_id == owner_id,
                AnalysisRevision.client_request_id == UUID(request_id),
            )
        )
        if row is None:
            return None
        if row.payload_sha256 != digest:
            raise ReviewConflict("request_reused")
        verified = await self.revisions.get(owner_id, row.chat_id, row.source_message_id, row.id)
        return verified.result

    async def current(self, owner_id, chat_id, message_id, base_id):
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
            raise ReviewConflict("case_busy")
        message = await self.revisions.owned_source(owner_id, chat_id, message_id)
        base = await self.revisions.get(owner_id, chat_id, message_id, UUID(base_id))
        latest = await self.db.scalar(
            select(AnalysisRevision.id)
            .where(
                AnalysisRevision.source_message_id == message_id,
                AnalysisRevision.owner_id == owner_id,
            )
            .order_by(AnalysisRevision.version.desc())
            .limit(1)
        )
        if latest != base.id or message.status != "completed" or message.analysis != base.result:
            raise ReviewConflict("stale_base")
        if freeze_snapshot(message.analysis)[1] != base.result_sha256:
            raise RevisionIntegrityError
        return ReviewBase(base.calculation_inputs, base.review)

    async def save(self, owner_id, chat_id, message_id, request_id, digest, inputs, result):
        row = await self.revisions.append(
            owner_id,
            chat_id,
            message_id,
            result,
            inputs,
            kind="human",
            client_request_id=UUID(request_id),
            payload_sha256=digest,
        )
        message = await self.revisions.owned_source(owner_id, chat_id, message_id)
        message.analysis = row.result
        chat = await self.db.get(Chat, chat_id)
        # The mapped onupdate timestamp fires when this field is explicitly touched.
        chat.updated_at = datetime.now(UTC)
        await self.db.flush()
        return row.result
