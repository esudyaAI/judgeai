from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeVerdictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str | None
    case_number: str | None
    court_name: str | None
    verdict_date: date | None
    source_type: str
    source_filename: str | None
    status: str
    created_at: datetime


class KnowledgeVerdictDetail(KnowledgeVerdictRead):
    file_hash: str | None
    structured: dict | None
    chunks_count: int


class PrecedentIndexRead(BaseModel):
    """What the regex reader recognised in an uploaded verdict (its precedent card)."""

    card_id: int
    qualifications: list[str]
    punishment_months: float | None
    conditional: bool
    recidivism: str | None


class KnowledgeUploadItem(BaseModel):
    verdict_id: int
    filename: str
    status: str
    duplicate: bool
    case_number: str | None
    court_name: str | None
    verdict_date: date | None
    warnings: list[str]
    extraction_status: str = "ok"
    extraction_issues: list[str] = Field(default_factory=list)
    unread_pages: list[int] = Field(default_factory=list)
    # None: no card (a private case document, or the same text is already a card elsewhere).
    precedent: PrecedentIndexRead | None = None


class KnowledgeUploadResponse(BaseModel):
    uploaded: int
    items: list[KnowledgeUploadItem]


class KnowledgeListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[KnowledgeVerdictRead]
