"""Read/check an owned frozen source context; there is deliberately no write port."""

from dataclasses import dataclass
from typing import Protocol

from src.domain.review_evidence import Evidence, ReviewDocument, ReviewSources, validate_evidence


@dataclass(frozen=True)
class RevisionSources:
    revision_id: str
    inputs_sha256: str
    documents: tuple[ReviewDocument, ...]
    context: ReviewSources


class ReviewSourceStore(Protocol):
    async def source_context(
        self, owner_id: int, chat_id: int, message_id: int, revision_id: str
    ) -> RevisionSources: ...


class ReadReviewSources:
    def __init__(self, store: ReviewSourceStore):
        self.store = store

    async def execute(self, owner_id, chat_id, message_id, revision_id):
        return await self.store.source_context(owner_id, chat_id, message_id, revision_id)


class CheckReviewEvidence(ReadReviewSources):
    async def execute(
        self, owner_id, chat_id, message_id, revision_id, subject_index: int, evidence: Evidence
    ):
        source = await super().execute(owner_id, chat_id, message_id, revision_id)
        validate_evidence(source.documents, source.context, subject_index, evidence)
        return source
