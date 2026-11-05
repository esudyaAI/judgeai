"""Ответ «замечание → основание» для одного замечания результата анализа (T15.7)."""

from typing import Literal

from pydantic import BaseModel

from src.schemas.analysis import LegalCheck


class CheckBasisRead(BaseModel):
    # index of the finding in result.legal_checks
    index: int
    # the finding exactly as stored in the result
    check: LegalCheck
    # T15.6 for this finding: current / changed / unknown (no stored version) / no_rule
    reference_status: Literal["current", "changed", "unknown", "no_rule"]
    current_basis_version: str | None
    # the same body as GET /api/legal/rules/{rule_key}[?on=]; None — the finding names no rule
    # or its rule is no longer in the reference
    basis: dict | None
