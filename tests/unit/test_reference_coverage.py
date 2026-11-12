"""T15.8: область поддержки справки — сводка статусов оснований всех правил (чистая логика)."""

import pytest

from src.domain.reference_coverage import STATUSES, RuleState, summarize_coverage


def state(key, status, review=True):
    return RuleState(key=key, basis_status=status, needs_legal_review=review)


def test_every_rule_is_counted_once_under_its_status():
    coverage = summarize_coverage(
        [
            state("b.rule", "no_basis"),
            state("a.rule", "no_basis"),
            state("c.rule", "verified"),
            state("d.rule", "outdated"),
        ]
    )
    assert coverage.total == 4
    assert coverage.by_status["no_basis"] == ["a.rule", "b.rule"]
    assert coverage.by_status["verified"] == ["c.rule"]
    assert coverage.by_status["outdated"] == ["d.rule"]
    assert sum(len(keys) for keys in coverage.by_status.values()) == coverage.total


def test_all_statuses_are_listed_even_when_empty_in_fixed_order():
    coverage = summarize_coverage([state("a.rule", "no_basis")])
    assert tuple(coverage.by_status) == STATUSES
    assert coverage.by_status["rejected"] == []


def test_only_verified_basis_is_confirmed():
    coverage = summarize_coverage(
        [
            state("a.rule", "verified"),
            state("b.rule", "period_unknown"),
            state("c.rule", "incomplete"),
            state("d.rule", "unreviewed"),
        ]
    )
    assert coverage.confirmed == ["a.rule"]
    assert coverage.unconfirmed == ["b.rule", "c.rule", "d.rule"]


def test_rules_needing_legal_review_are_listed_separately():
    coverage = summarize_coverage(
        [state("b.rule", "verified", review=True), state("a.rule", "verified", review=False)]
    )
    assert coverage.confirmed == ["a.rule", "b.rule"]
    assert coverage.needs_legal_review == ["b.rule"]


def test_unknown_status_is_an_error_not_silently_dropped():
    with pytest.raises(ValueError, match="mystery"):
        summarize_coverage([state("a.rule", "mystery")])


def test_duplicate_key_is_an_error():
    with pytest.raises(ValueError, match="a.rule"):
        summarize_coverage([state("a.rule", "verified"), state("a.rule", "no_basis")])


def test_empty_catalog_gives_empty_coverage():
    coverage = summarize_coverage([])
    assert coverage.total == 0
    assert coverage.confirmed == [] and coverage.unconfirmed == []
    assert all(keys == [] for keys in coverage.by_status.values())
