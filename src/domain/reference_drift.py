"""Domain — has the rule reference changed since an analysis was made (T15.6).

An analysis stores the fingerprints of the reference it was made with (T15.5): the catalog version
and, for every finding built by a rule, that rule's basis version. Comparing them with the current
fingerprints (T15.4) tells a reader whether the conclusions still rest on the same reference, and
which findings now rest on a changed basis. A result that recorded no version is `unknown`, never
reported as current.

T15.11 — the same comparison for one stored version (the sanction data fingerprint of T15.10):
`compare_version` tells whether the sanctions the checks read have changed since the analysis.

T15.12 — per article: the sanction data fingerprint covers every article, so a change of any
other article read as `changed`. `compare_article_versions` compares only the articles whose
sanctions the analysis read; an article whose reading is gone from the reference is `removed`.
"""

from dataclasses import dataclass, field
from typing import Literal

from src.domain.sanction_coverage import article_sort_key

ReferenceStatus = Literal["current", "changed", "unknown"]
CheckStatus = Literal["current", "changed", "unknown", "no_rule"]
ArticleStatus = Literal["current", "changed", "removed"]


@dataclass(frozen=True)
class StoredCheck:
    """What a stored finding remembers: its catalog rule and that rule's basis version."""

    rule_key: str | None
    basis_version: str | None


@dataclass(frozen=True)
class CheckDrift:
    index: int
    rule_key: str | None
    basis_version: str | None
    current_basis_version: str | None
    status: CheckStatus


@dataclass(frozen=True)
class VersionDrift:
    """One fingerprint stored in a result against the current one."""

    status: ReferenceStatus
    stored_version: str | None
    current_version: str


@dataclass(frozen=True)
class ArticleDrift:
    """The stored version of one article's sanctions against its current version."""

    article: str
    stored_version: str
    current_version: str | None
    status: ArticleStatus


@dataclass(frozen=True)
class ArticlesDrift:
    status: ReferenceStatus
    articles: list[ArticleDrift] = field(default_factory=list)
    # changed or removed, in article number order
    changed_articles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceDrift:
    status: ReferenceStatus
    stored_version: str | None
    current_version: str
    checks: list[CheckDrift] = field(default_factory=list)
    changed_rules: list[str] = field(default_factory=list)
    # T15.11: the sanction data version; None — not compared
    sanctions: VersionDrift | None = None
    # T15.12: the sanctions of the articles the analysis read; None — not compared
    sanction_articles: ArticlesDrift | None = None


def compare_version(stored_version: str | None, current_version: str) -> VersionDrift:
    """`unknown` when nothing was stored; otherwise `current` only for the very same version."""
    if stored_version is None:
        status: ReferenceStatus = "unknown"
    else:
        status = "current" if stored_version == current_version else "changed"
    return VersionDrift(status, stored_version, current_version)


def compare_article_versions(
    stored: dict[str, str] | None, current: dict[str, str]
) -> ArticlesDrift:
    """`unknown` when nothing was stored; `current` only if every read article is unchanged.

    An analysis that read no sanctions stored `{}` — nothing it rests on can change.
    """
    if stored is None:
        return ArticlesDrift("unknown")
    drifts = []
    for article in sorted(stored, key=article_sort_key):
        now = current.get(article)
        if now is None:
            status: ArticleStatus = "removed"
        else:
            status = "current" if now == stored[article] else "changed"
        drifts.append(ArticleDrift(article, stored[article], now, status))
    changed = [d.article for d in drifts if d.status != "current"]
    return ArticlesDrift("changed" if changed else "current", drifts, changed)


def _check_status(check: StoredCheck, current: str | None) -> CheckStatus:
    if check.rule_key is None:
        return "no_rule"
    if check.basis_version is None:
        return "unknown"
    # a rule dropped from the reference (current is None) also counts as a changed basis
    return "current" if check.basis_version == current else "changed"


def compare_reference(
    stored_version: str | None,
    checks: list[StoredCheck],
    current_version: str,
    current_rules: dict[str, str],
) -> ReferenceDrift:
    """Compare the versions stored in a result with the current reference fingerprints."""
    drifts = []
    for index, check in enumerate(checks):
        current = current_rules.get(check.rule_key) if check.rule_key else None
        drifts.append(
            CheckDrift(
                index=index,
                rule_key=check.rule_key,
                basis_version=check.basis_version,
                current_basis_version=current,
                status=_check_status(check, current),
            )
        )
    changed = sorted({d.rule_key for d in drifts if d.status == "changed" and d.rule_key})
    return ReferenceDrift(
        status=compare_version(stored_version, current_version).status,
        stored_version=stored_version,
        current_version=current_version,
        checks=drifts,
        changed_rules=changed,
    )
