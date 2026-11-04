"""Save a human decision through the same calculator and an atomic case-locked store."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from src.domain.fact_review import FactDecision, InvalidReview, ReviewConflict, apply_decisions
from src.domain.prepared_legal import PreparedLegalInputs
from src.domain.prepared_sentencing import PreparedSentencingInputs
from src.domain.reports import freeze_snapshot
from src.domain.review_evidence import ReviewDocument, ReviewSources


@dataclass(frozen=True)
class ReviewBase:
    inputs: dict
    previous_review: dict


@dataclass(frozen=True)
class PreparedReview:
    legal: dict[int, PreparedLegalInputs]
    sentencing: dict[int, PreparedSentencingInputs]
    documents: tuple[ReviewDocument, ...]
    context: ReviewSources


class FactReviewStore(Protocol):
    async def lock_source(self, owner_id: int, chat_id: int, message_id: int): ...
    async def request(self, owner_id: int, request_id: str, digest: str) -> dict | None: ...
    async def current(
        self, owner_id: int, chat_id: int, message_id: int, base_id: str
    ) -> ReviewBase: ...
    async def save(
        self,
        owner_id: int,
        chat_id: int,
        message_id: int,
        request_id: str,
        digest: str,
        inputs: dict,
        result: dict,
    ) -> dict: ...


class ReviewCalculator(Protocol):
    def prepare(self, inputs: dict) -> PreparedReview: ...
    def calculate(
        self, inputs: dict, legal: dict, sentencing: dict, changed: bool
    ) -> tuple[dict, dict]: ...
    async def refresh_practice(self, payload: dict, result: dict) -> tuple[dict, dict]: ...


class SaveFactReview:
    def __init__(self, store: FactReviewStore, calculator: ReviewCalculator):
        self.store, self.calculator = store, calculator

    async def execute(
        self,
        owner_id,
        chat_id,
        message_id,
        base_id,
        request_id,
        decisions: tuple[FactDecision, ...],
    ):
        try:
            digest = freeze_snapshot(
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "base_revision_id": base_id,
                    "decisions": [asdict(d) for d in decisions],
                }
            )[1]
        except (TypeError, ValueError):
            raise InvalidReview("invalid_value") from None
        await self.store.lock_source(owner_id, chat_id, message_id)
        existing = await self.store.request(owner_id, request_id, digest)
        if existing is not None:
            return existing
        base = await self.store.current(owner_id, chat_id, message_id, base_id)
        prepared = self.calculator.prepare(base.inputs)
        legal, sentencing, audit, changed = apply_decisions(
            prepared.legal, prepared.sentencing, prepared.documents, prepared.context, decisions
        )
        inputs, result = self.calculator.calculate(base.inputs, legal, sentencing, changed)
        inputs, result = await self.calculator.refresh_practice(inputs, result)
        previous = base.previous_review.get("decisions", [])
        if not isinstance(previous, list):
            raise ReviewConflict("invalid_review_history")
        timestamp = datetime.now(UTC).isoformat()
        result["human_review"] = {
            "status": "partially_reviewed",
            "actor_id": owner_id,
            "reviewed_at": timestamp,
            "base_revision_id": base_id,
            "decisions": [
                *previous,
                *[
                    {
                        **item,
                        "actor_id": owner_id,
                        "reviewed_at": timestamp,
                        "base_revision_id": base_id,
                    }
                    for item in audit
                ],
            ],
            "legal_approval": False,
            "practice_invalidated": any(
                state.get("status") == "unavailable"
                for state in (
                    (inputs.get("review_practice_refresh") or {}).get("subjects") or {}
                ).values()
            ),
        }
        return await self.store.save(
            owner_id, chat_id, message_id, request_id, digest, inputs, result
        )
