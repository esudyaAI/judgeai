from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr
from sqlalchemy.exc import IntegrityError

from src.api.deps import CurrentUser, DbSession
from src.application.fact_review import SaveFactReview
from src.application.review_evidence import CheckReviewEvidence, ReadReviewSources
from src.domain.analysis_revisions import RevisionIntegrityError, RevisionNotFound
from src.domain.fact_review import FactDecision, InvalidReview, ReviewConflict, review_catalog
from src.domain.review_evidence import Evidence, InvalidEvidence
from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
from src.infrastructure.fact_review import FrozenReviewCalculator, SqlFactReviewStore
from src.infrastructure.review_sources import SqlReviewSourceStore

router = APIRouter()


class RevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chat_id: int
    source_message_id: int
    version: int
    base_revision_id: UUID | None
    kind: str
    inputs_sha256: str | None
    result_sha256: str
    created_at: datetime


class RevisionDetail(RevisionSummary):
    calculation_inputs: dict | None
    result: dict
    review: dict


@router.get("/{chat_id}/messages/{message_id}/revisions", response_model=list[RevisionSummary])
async def list_revisions(
    chat_id: int,
    message_id: int,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        return await SqlAnalysisRevisionStore(db).list(
            user.user_id, chat_id, message_id, limit, offset
        )
    except RevisionNotFound:
        raise HTTPException(404, "Результат не найден") from None


@router.get(
    "/{chat_id}/messages/{message_id}/revisions/{revision_id}", response_model=RevisionDetail
)
async def get_revision(
    chat_id: int, message_id: int, revision_id: UUID, db: DbSession, user: CurrentUser
):
    try:
        return await SqlAnalysisRevisionStore(db).get(
            user.user_id, chat_id, message_id, revision_id
        )
    except RevisionNotFound:
        raise HTTPException(404, "Версия результата не найдена") from None
    except RevisionIntegrityError:
        raise HTTPException(409, "Нарушена целостность сохранённой версии") from None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_index: StrictInt
    document_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: StrictInt
    end: StrictInt
    quote: str = Field(min_length=1, max_length=4000)


class EvidenceCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_index: StrictInt
    evidence: EvidenceRead


def _source_error(exc):
    if isinstance(exc, RevisionNotFound):
        return HTTPException(404, "Версия результата не найдена")
    if isinstance(exc, RevisionIntegrityError):
        return HTTPException(409, "Нарушена целостность сохранённой версии")
    if str(exc) == "unsupported_snapshot":
        return HTTPException(
            409, "Для проверки источников выполните новый анализ. Старая версия сохранена."
        )
    return HTTPException(
        422, "Цитата, координаты или область выбранного лица не соответствуют снимку."
    )


@router.get("/{chat_id}/messages/{message_id}/revisions/{revision_id}/sources")
async def get_revision_sources(
    chat_id: int, message_id: int, revision_id: UUID, db: DbSession, user: CurrentUser
):
    try:
        source = await ReadReviewSources(SqlReviewSourceStore(db)).execute(
            user.user_id, chat_id, message_id, str(revision_id)
        )
        return asdict(source)
    except (RevisionNotFound, RevisionIntegrityError, InvalidEvidence) as exc:
        raise _source_error(exc) from None


@router.post("/{chat_id}/messages/{message_id}/revisions/{revision_id}/evidence/check")
async def check_revision_evidence(
    chat_id: int,
    message_id: int,
    revision_id: UUID,
    body: EvidenceCheckRequest,
    db: DbSession,
    user: CurrentUser,
):
    try:
        source = await CheckReviewEvidence(SqlReviewSourceStore(db)).execute(
            user.user_id,
            chat_id,
            message_id,
            str(revision_id),
            body.subject_index,
            Evidence(**body.evidence.model_dump()),
        )
        return {
            "source_matches": True,
            "revision_id": source.revision_id,
            "inputs_sha256": source.inputs_sha256,
        }
    except (RevisionNotFound, RevisionIntegrityError, InvalidEvidence) as exc:
        raise _source_error(exc) from None


class FactDecisionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str = Field(min_length=1, max_length=200)
    operation: Literal["confirm", "correct", "unknown"]
    reason: str = Field(min_length=1, max_length=2000)
    value: StrictStr | StrictBool | StrictInt | StrictFloat | dict | None = None
    evidence: EvidenceRead | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision_id: UUID
    client_request_id: UUID
    decisions: list[FactDecisionRead] = Field(min_length=1, max_length=200)


@router.get("/{chat_id}/messages/{message_id}/revisions/{revision_id}/facts")
async def get_review_facts(
    chat_id: int, message_id: int, revision_id: UUID, db: DbSession, user: CurrentUser
):
    try:
        row = await SqlAnalysisRevisionStore(db).get(user.user_id, chat_id, message_id, revision_id)
        prepared = FrozenReviewCalculator().prepare(row.calculation_inputs)
        return [asdict(spec) for spec in review_catalog(prepared.legal, prepared.sentencing)]
    except (RevisionNotFound, RevisionIntegrityError, InvalidEvidence) as exc:
        raise _source_error(exc) from None
    except ReviewConflict:
        raise HTTPException(
            409, "Для проверки фактов выполните новый анализ. Старая версия сохранена."
        ) from None


@router.post("/{chat_id}/messages/{message_id}/review")
async def save_fact_review(
    chat_id: int, message_id: int, body: ReviewRequest, db: DbSession, user: CurrentUser
):
    decisions = tuple(
        FactDecision(
            item.fact_id,
            item.operation,
            item.reason,
            item.value,
            Evidence(**item.evidence.model_dump()) if item.evidence is not None else None,
        )
        for item in body.decisions
    )
    try:
        result = await SaveFactReview(SqlFactReviewStore(db), FrozenReviewCalculator()).execute(
            user.user_id,
            chat_id,
            message_id,
            str(body.base_revision_id),
            str(body.client_request_id),
            decisions,
        )
        await db.commit()
        return result
    except (RevisionNotFound, RevisionIntegrityError, InvalidEvidence) as exc:
        await db.rollback()
        raise _source_error(exc) from None
    except ReviewConflict:
        await db.rollback()
        raise HTTPException(
            409,
            "Версия изменилась, анализ выполняется или ключ запроса уже использован. "
            "Обновите историю.",
        ) from None
    except InvalidReview:
        await db.rollback()
        raise HTTPException(
            422, "Проверьте выбранное поле, значение, действие и причину."
        ) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, "Конфликт сохранения версии. Обновите историю и повторите запрос."
        ) from None
    except Exception:
        await db.rollback()
        raise HTTPException(
            503, "Не удалось сохранить проверку. Повторите тот же запрос."
        ) from None
