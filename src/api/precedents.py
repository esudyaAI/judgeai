"""HTTP: practice verdicts similar to the draft attached to a case."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.deps import CurrentUser, DbSession
from src.application.precedent_cards import query_card
from src.application.similar_precedents import EmbeddingPort, FindSimilarPrecedents
from src.db.models import Chat, Message
from src.infrastructure.bounded_embedder import BoundedQueryEmbedder
from src.infrastructure.fastembed_embedder import FastembedEmbedder
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
            for item in found.items
        ],
        candidates=found.candidates,
        excluded=found.excluded,
        vector_used=found.vector_used,
        note=None if query.episodes else "В проекте не найдена квалификация; поиск неточен.",
    )
