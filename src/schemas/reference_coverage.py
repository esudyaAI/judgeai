from datetime import date

from pydantic import BaseModel


class ReferenceCoverageRead(BaseModel):
    """T15.8: область поддержки справки — статусы оснований всех правил каталога."""

    version: str
    on: date | None
    total: int
    by_status: dict[str, list[str]]
    confirmed: list[str]
    unconfirmed: list[str]
    needs_legal_review: list[str]
