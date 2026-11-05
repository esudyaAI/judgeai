"""Domain Layer — область поддержки справки (T15.8).

Сводка по всем правилам каталога: у каких правил основание подтверждено, а какие проверяются
без подтверждённой нормы (нет связи, связь не сверена, норма не действовала на дату, период
неизвестен). Чистая логика без фреймворков и БД: статусы оснований приходят из справки
(src/services/legal_rule_catalog.py), здесь они только группируются. Ни одно правило не
пропадает из сводки, неизвестный статус — ошибка, а не молчаливый пропуск.
"""

from dataclasses import dataclass

STATUSES: tuple[str, ...] = (
    "verified",
    "incomplete",
    "period_unknown",
    "unreviewed",
    "outdated",
    "rejected",
    "no_basis",
)
CONFIRMED = "verified"


@dataclass(frozen=True)
class RuleState:
    key: str
    basis_status: str
    needs_legal_review: bool


@dataclass(frozen=True)
class ReferenceCoverage:
    total: int
    by_status: dict[str, list[str]]
    confirmed: list[str]
    unconfirmed: list[str]
    needs_legal_review: list[str]


def summarize_coverage(rules: list[RuleState]) -> ReferenceCoverage:
    """Group rule keys by basis status; every status is present, keys are sorted."""
    by_status: dict[str, list[str]] = {status: [] for status in STATUSES}
    seen: set[str] = set()
    for rule in rules:
        if rule.basis_status not in by_status:
            raise ValueError(f"unknown basis status: {rule.basis_status}")
        if rule.key in seen:
            raise ValueError(f"duplicate rule key: {rule.key}")
        seen.add(rule.key)
        by_status[rule.basis_status].append(rule.key)
    for keys in by_status.values():
        keys.sort()
    return ReferenceCoverage(
        total=len(seen),
        by_status=by_status,
        confirmed=list(by_status[CONFIRMED]),
        unconfirmed=sorted(seen - set(by_status[CONFIRMED])),
        needs_legal_review=sorted(rule.key for rule in rules if rule.needs_legal_review),
    )
