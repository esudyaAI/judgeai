"""HTTP: practice verdicts similar to the draft attached to a case."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.deps import CurrentUser, DbSession
from src.application.precedent_cards import query_card
from src.application.similar_precedents import EmbeddingPort, FindSimilarPrecedents
from src.db.models import Chat, Message
from src.domain.analysis_revisions import RevisionIntegrityError, RevisionNotFound
from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
from src.infrastructure.bounded_embedder import BoundedQueryEmbedder
from src.infrastructure.calculation_inputs import load_inputs
from src.infrastructure.fastembed_embedder import FastembedEmbedder, with_embedding_materials
from src.infrastructure.frozen_practice import POOL_WARNING
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import RegexVerdictReader
from src.schemas.precedents import (
    FilterRead,
    PrecedentRead,
    PrecedentSearchRead,
    QueryCardRead,
)
from src.services.defendant_blocks import scoped_verdicts

router = APIRouter()


def get_embedder() -> EmbeddingPort:
    return BoundedQueryEmbedder(FastembedEmbedder())


async def _draft_texts(db, chat_id: int) -> list[str]:
    """Texts of the latest user message with readable attachments, newest first."""
    messages = await db.scalars(
        select(Message)
        .options(selectinload(Message.attachments))
        .where(Message.chat_id == chat_id, Message.role == "user")
        .order_by(Message.id.desc())
    )
    for message in messages:
        texts = [a.extracted_text for a in message.attachments if (a.extracted_text or "").strip()]
        if texts:
            return texts
    return []


@router.get("/{chat_id}/precedents", response_model=PrecedentSearchRead)
async def similar_precedents(
    chat_id: int,
    db: DbSession,
    user: CurrentUser,
    embedder: EmbeddingPort = Depends(get_embedder),
    limit: int = Query(10, ge=1, le=50),
    defendant: int | None = Query(None, ge=1),
):
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id))
    if chat is None:
        raise HTTPException(status_code=404, detail="Чат не найден")
    latest = await db.scalar(
        select(Message)
        .where(Message.chat_id == chat_id, Message.role == "assistant")
        .order_by(Message.id.desc())
        .limit(1)
    )
    if latest is not None and latest.status in ("pending", "running"):
        return _empty("Дождитесь завершения текущего анализа.")
    if (
        latest is not None
        and isinstance(latest.analysis, dict)
        and (latest.analysis.get("human_review") or {}).get("status") == "partially_reviewed"
    ):
        return await _reviewed_practice(db, user.user_id, chat_id, latest, defendant, limit)
    texts = await _draft_texts(db, chat_id)
    if not texts:
        return PrecedentSearchRead(
            query=None,
            items=[],
            candidates=0,
            excluded=0,
            vector_used=False,
            note="В деле нет загруженных документов с текстом.",
        )
    embedder = with_embedding_materials(embedder, tuple(texts))
    people = [person for text in texts for person in scoped_verdicts(text)]
    if people and defendant is None:
        return PrecedentSearchRead(
            query=None,
            items=[],
            candidates=0,
            excluded=0,
            vector_used=False,
            note=(
                "В приговоре несколько осуждённых. Выберите номер осуждённого "
                "параметром defendant; общая карточка не строится."
            ),
        )
    if defendant is not None:
        if defendant > (len(people) if people else 1):
            raise HTTPException(status_code=422, detail="Номер осуждённого вне диапазона")
        if people:
            texts = [people[defendant - 1][1]]
    query = query_card(RegexVerdictReader(), texts)
    found = await FindSimilarPrecedents(SqlPrecedentStore(db), embedder).execute(query, limit)
    return _search_read(
        query,
        found.items,
        found.candidates,
        found.excluded,
        found.vector_used,
        None if query.episodes else "В проекте не найдена квалификация; поиск неточен.",
    )


def _search_read(query, items, candidates, excluded, vector_used, note):
    return PrecedentSearchRead(
        query=QueryCardRead(
            qualifications=[str(e.qualification) for e in query.episodes],
            mitigating=sorted(query.mitigating),
            aggravating=sorted(query.aggravating),
            recidivism=query.recidivism.value if query.recidivism else None,
        ),
        items=[
            PrecedentRead(
                card_id=item.stored.id,
                court_name=item.stored.court_name,
                decision_date=item.stored.decision_date.isoformat()
                if item.stored.decision_date
                else None,
                uid=item.stored.uid,
                source_url=item.stored.source_url,
                qualifications=[str(e.qualification) for e in item.stored.card.episodes],
                punishment_months=item.stored.card.imprisonment_months,
                conditional=item.stored.card.conditional,
                recidivism=item.stored.card.recidivism.value
                if item.stored.card.recidivism
                else None,
                score=item.score,
                breakdown=item.breakdown,
                filters=[
                    FilterRead(
                        name=f.name, state=f.state.value, reason=f.reason, action=f.action.value
                    )
                    for f in item.filters
                ],
                channels=list(item.channels),
                text_similarity=item.text_similarity,
            )
            for item in items
        ],
        candidates=candidates,
        excluded=excluded,
        vector_used=vector_used,
        note=note,
    )


def _empty(note):
    return PrecedentSearchRead(
        query=None, items=[], candidates=0, excluded=0, vector_used=False, note=note
    )


async def _reviewed_practice(db, owner_id, chat_id, message, defendant, limit):
    try:
        revision = await SqlAnalysisRevisionStore(db).get(
            owner_id, chat_id, message.id, UUID(message.analysis["revision"]["id"])
        )
        snapshot = load_inputs(revision.calculation_inputs)
    except RevisionNotFound:
        raise HTTPException(404, "Версия результата не найдена") from None
    except (RevisionIntegrityError, KeyError, TypeError, ValueError):
        raise HTTPException(
            409, "Сохранённая практика недоступна; проверьте историю версии."
        ) from None
    scopes = snapshot.kwargs.prepared_sentencing_inputs
    if len(scopes) > 1 and defendant is None:
        return _empty(
            "В приговоре несколько осуждённых. Выберите номер осуждённого "
            "параметром defendant; общая карточка не строится."
        )
    subject = defendant - 1 if defendant is not None else 0
    if subject not in scopes:
        raise HTTPException(422, "Номер осуждённого вне диапазона")
    report = (
        (snapshot.kwargs.defendant_practice or {}).get(subject)
        if len(scopes) > 1
        else snapshot.kwargs.practice
    )
    if "practice" in snapshot.review_invalidations:
        report = None
    if report is None:
        state = ((snapshot.review_practice_refresh or {}).get("subjects") or {}).get(
            str(subject), {}
        )
        return _empty(
            "После исправления фактов сравнение с практикой недоступно. "
            + state.get("reason", "Для этой версии нет сохранённой выборки.")
        )
    note = (
        POOL_WARNING
        if snapshot.review_practice_refresh
        else "Сохранённая практика выбранной версии; новый поиск не выполнялся."
    )
    if (((snapshot.review_practice_refresh or {}).get("subjects") or {}).get(str(subject), {})).get(
        "basis"
    ) == "shown_only":
        note += " Сохранён только ранее показанный список аналогов."
    retained = {item.stored.id: item for item in report.shown}
    for item in report.candidate_pool:
        retained.setdefault(item.stored.id, item)
    return _search_read(
        report.query,
        list(retained.values())[:limit],
        report.candidates,
        report.excluded,
        report.vector_used,
        note,
    )
