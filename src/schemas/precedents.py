from pydantic import BaseModel


class FilterRead(BaseModel):
    name: str
    state: str
    reason: str
    action: str


class PrecedentRead(BaseModel):
    card_id: int
    court_name: str | None
    decision_date: str | None
    uid: str | None
    source_url: str | None
    qualifications: list[str]
    punishment_months: float | None
    conditional: bool
    recidivism: str | None
    score: float
    breakdown: dict[str, dict[str, float]]
    filters: list[FilterRead]
    channels: list[str]
    text_similarity: float | None


class QueryCardRead(BaseModel):
    qualifications: list[str]
    mitigating: list[str]
    aggravating: list[str]
    recidivism: str | None


class PrecedentSearchRead(BaseModel):
    query: QueryCardRead | None
    items: list[PrecedentRead]
    candidates: int
    excluded: int
    vector_used: bool
    note: str | None = None
