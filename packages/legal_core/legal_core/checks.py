# Domain Layer — result of a single legal check.
from dataclasses import dataclass
from enum import StrEnum


class CheckStatus(StrEnum):
    OK = "ok"
    POSSIBLE_VIOLATION = "possible_violation"  # the system flags, the judge decides (п. 2.5.3)
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class CheckResult:
    norm: str
    status: CheckStatus
    explanation: str
    source: str  # official text + edition the rule was written against
    needs_legal_review: bool = True
    rule_key: str | None = None  # key in legal_core.catalog — opens the rule's legal basis
