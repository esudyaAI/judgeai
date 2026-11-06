"""Ответ сверки версии справки результата анализа с текущей (T15.6; санкции — T15.11/T15.12)."""

from typing import Literal

from pydantic import BaseModel


class CheckReferenceStatus(BaseModel):
    # index of the finding in result.legal_checks
    index: int
    rule_key: str | None
    basis_version: str | None
    current_basis_version: str | None
    status: Literal["current", "changed", "unknown", "no_rule"]


class VersionStatusRead(BaseModel):
    status: Literal["current", "changed", "unknown"]
    stored_version: str | None
    current_version: str


class ArticleSanctionStatusRead(BaseModel):
    article: str
    stored_version: str
    # None — the article has no parsed sanctions any more
    current_version: str | None
    status: Literal["current", "changed", "removed"]


class SanctionArticlesStatusRead(BaseModel):
    # current — every article the analysis read is unchanged; unknown — not recorded
    status: Literal["current", "changed", "unknown"]
    changed_articles: list[str]
    articles: list[ArticleSanctionStatusRead]


class ReferenceStatusRead(BaseModel):
    # current — the result was made with the current reference; changed — the reference has
    # changed since; unknown — the result recorded no version (stored before T15.5).
    status: Literal["current", "changed", "unknown"]
    stored_version: str | None
    current_version: str
    changed_rules: list[str]
    checks: list[CheckReferenceStatus]
    # T15.11: has the sanction data (GET /api/legal/rules/coverage, sanctions.version) changed
    # since the analysis; unknown — the result recorded no sanction version.
    sanctions: VersionStatusRead
    # T15.12: only the articles whose sanctions the analysis read; a change of another
    # article changes `sanctions` but not this block.
    sanction_articles: SanctionArticlesStatusRead
