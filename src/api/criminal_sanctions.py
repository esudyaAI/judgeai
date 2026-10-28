"""Read-only access to structured УК РФ sanctions with their provenance."""

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import DbSession
from src.schemas.criminal_sanctions import CriminalSanctionRead
from src.services.criminal_sanction_lookup import find_article_sanctions

router = APIRouter()


@router.get("", response_model=list[CriminalSanctionRead])
async def list_article_sanctions(
    db: DbSession,
    article: str = Query(min_length=1, max_length=20, pattern=r"^\d+(?:\.\d+)*$"),
    part: int | None = Query(default=None, ge=1, le=99),
):
    """Sanctions of an article (optionally one part) from the newest parsed edition."""
    reading = await find_article_sanctions(db, article, part)
    if reading is None:
        raise HTTPException(404, "Для этой статьи санкции не разобраны")
    return [
        CriminalSanctionRead(
            article=s.article,
            part=s.part,
            kind=s.kind.value,
            role=s.role.value,
            min_value=s.min_value,
            max_value=s.max_value,
            unit=s.unit.value if s.unit else None,
            clause=s.clause,
            provenance=reading.provenance,
        )
        for s in reading.sanctions
    ]
