import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import KnowledgeChunk, KnowledgeVerdict
from src.domain.practice import PRIVATE_SOURCE_TYPES
from src.services.embeddings import embed_query

logger = logging.getLogger(__name__)


async def _vector_search(
    db: AsyncSession,
    query_vector: list[float],
    limit: int,
) -> list[dict]:
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)

    stmt = (
        select(KnowledgeChunk, KnowledgeVerdict, distance.label("distance"))
        .join(
            KnowledgeVerdict,
            KnowledgeChunk.verdict_id == KnowledgeVerdict.id,
        )
        .where(
            KnowledgeChunk.embedding.is_not(None),
            KnowledgeVerdict.source_type.not_in(PRIVATE_SOURCE_TYPES),
        )
        .order_by(distance.asc())
        .limit(limit * 3)
    )

    result = await db.execute(stmt)

    seen: set[int] = set()
    items: list[dict] = []

    for row in result.all():
        chunk, verdict, dist = row

        if verdict.id in seen:
            continue

        seen.add(verdict.id)

        items.append(
            {
                "verdict_id": verdict.id,
                "case_number": verdict.case_number,
                "court_name": verdict.court_name,
                "verdict_date": verdict.verdict_date.isoformat() if verdict.verdict_date else None,
                "score": round(max(0.0, 1.0 - float(dist)), 4),
                "excerpt": chunk.content[:300],
            }
        )

        if len(items) >= limit:
            break

    return items


async def _keyword_fallback(
    db: AsyncSession,
    query: str,
    limit: int,
) -> list[dict]:
    words = [word for word in query.split() if len(word) >= 5][:5]

    if not words:
        return []

    conditions = [KnowledgeChunk.content.ilike(f"%{word}%") for word in words]

    stmt = (
        select(KnowledgeVerdict)
        .join(KnowledgeChunk, KnowledgeChunk.verdict_id == KnowledgeVerdict.id)
        .where(or_(*conditions), KnowledgeVerdict.source_type.not_in(PRIVATE_SOURCE_TYPES))
        .distinct()
        .limit(limit)
    )

    verdicts = await db.scalars(stmt)

    return [
        {
            "verdict_id": verdict.id,
            "case_number": verdict.case_number,
            "court_name": verdict.court_name,
            "verdict_date": verdict.verdict_date.isoformat() if verdict.verdict_date else None,
            "score": None,
            "excerpt": (verdict.raw_text or "")[:300],
        }
        for verdict in verdicts
    ]


async def find_similar_verdicts(
    db: AsyncSession,
    query_text: str,
    document_texts: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    query = query_text.strip()

    if not query and document_texts:
        query = next((text for text in document_texts if text.strip()), "")

    query = query[:5000]

    if not query:
        return []

    query_vector: list[float] | None = None

    try:
        query_vector = await embed_query(query)
    except Exception:
        logger.warning("query embedding failed, falling back to keyword search", exc_info=True)
        query_vector = None

    if query_vector:
        try:
            items = await _vector_search(db, query_vector, limit)

            if items:
                return items
        except Exception:
            logger.warning("vector search failed, falling back to keyword search", exc_info=True)

    return await _keyword_fallback(db, query, limit)
