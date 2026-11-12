from datetime import date

from pydantic import BaseModel


class SanctionCoverageRead(BaseModel):
    """T15.9: охват санкций — статьи УК с разобранными санкциями по статусу их редакции.

    `version` (T15.10) — отпечаток данных санкций, не зависит от `on`; `version` сводки —
    по-прежнему версия каталога правил.
    """

    version: str
    total_articles: int
    by_status: dict[str, list[str]]
    confirmed: list[str]
    unconfirmed: list[str]


class ReferenceCoverageRead(BaseModel):
    """T15.8: область поддержки справки — статусы оснований всех правил каталога."""

    version: str
    on: date | None
    total: int
    by_status: dict[str, list[str]]
    confirmed: list[str]
    unconfirmed: list[str]
    needs_legal_review: list[str]
    sanctions: SanctionCoverageRead
