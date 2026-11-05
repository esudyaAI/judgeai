"""Ответ сверки версии справки результата анализа с текущей (T15.6)."""

from typing import Literal

from pydantic import BaseModel


class CheckReferenceStatus(BaseModel):
    # index of the finding in result.legal_checks
    index: int
    rule_key: str | None
    basis_version: str | None
    current_basis_version: str | None
    status: Literal["current", "changed", "unknown", "no_rule"]


class ReferenceStatusRead(BaseModel):
    # current — the result was made with the current reference; changed — the reference has
    # changed since; unknown — the result recorded no version (stored before T15.5).
    status: Literal["current", "changed", "unknown"]
    stored_version: str | None
    current_version: str
    changed_rules: list[str]
    checks: list[CheckReferenceStatus]
