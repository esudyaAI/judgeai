from pydantic import BaseModel


class PracticeFactSourceRead(BaseModel):
    card_id: int
    court_name: str | None
    decision_date: str | None
    uid: str | None
    source_url: str | None
    months: float | None
    conditional: bool


class PracticeFactRead(BaseModel):
    answered: bool
    method: str = "code"
    hint: str | None = None
    text: str | None = None
    qualification: str | None = None
    found: int = 0
    counted: int = 0
    excluded: int = 0
    with_term: int = 0
    enough_data: bool = False
    mean_months: float | None = None
    median_months: float | None = None
    p25_months: float | None = None
    p75_months: float | None = None
    min_months: float | None = None
    max_months: float | None = None
    conditional_share: float | None = None
    sources: list[PracticeFactSourceRead] = []
