"""T15.9: охват санкций по статьям — чистая логика сводки."""

import pytest

from src.domain.sanction_coverage import (
    SANCTION_STATUSES,
    ArticleSanctionState,
    article_status,
    newest_readings,
    summarize_sanction_coverage,
)


def state(article, status="unreviewed", in_force=None):
    return ArticleSanctionState(article=article, edition_status=status, in_force=in_force)


@pytest.mark.parametrize(
    ("edition_status", "in_force", "dated", "expected"),
    [
        ("verified", None, False, "verified"),
        ("verified", True, True, "verified"),
        ("verified", None, True, "period_unknown"),
        ("verified", False, True, "outdated"),
        ("unreviewed", None, False, "unreviewed"),
        ("unreviewed", True, True, "unreviewed"),
        ("unreviewed", False, True, "outdated"),
        ("rejected", None, False, "rejected"),
        ("rejected", True, True, "rejected"),
    ],
)
def test_article_status(edition_status, in_force, dated, expected):
    assert article_status(state("158", edition_status, in_force), dated=dated) == expected


def test_without_date_in_force_is_ignored():
    assert article_status(state("158", "verified", False), dated=False) == "verified"


def test_every_article_under_one_status_in_fixed_order():
    coverage = summarize_sanction_coverage(
        [
            state("228.1", "verified"),
            state("158", "unreviewed"),
            state("30", "rejected"),
            state("228", "verified"),
        ],
        dated=False,
    )
    assert tuple(coverage.by_status) == SANCTION_STATUSES
    assert coverage.total_articles == 4
    assert coverage.by_status["verified"] == ["228", "228.1"]
    assert coverage.by_status["unreviewed"] == ["158"]
    assert coverage.by_status["rejected"] == ["30"]
    assert coverage.by_status["outdated"] == coverage.by_status["period_unknown"] == []
    assert coverage.confirmed == ["228", "228.1"]
    assert coverage.unconfirmed == ["30", "158"]


def test_articles_sort_by_number_not_text():
    coverage = summarize_sanction_coverage(
        [state("264.1"), state("30"), state("105"), state("264")], dated=False
    )
    assert coverage.unconfirmed == ["30", "105", "264", "264.1"]


def test_only_verified_in_force_is_confirmed_on_date():
    coverage = summarize_sanction_coverage(
        [
            state("158", "verified", True),
            state("159", "verified", None),
            state("161", "verified", False),
        ],
        dated=True,
    )
    assert coverage.confirmed == ["158"]
    assert coverage.by_status["period_unknown"] == ["159"]
    assert coverage.by_status["outdated"] == ["161"]
    assert coverage.unconfirmed == ["159", "161"]


def test_unknown_edition_status_and_duplicate_article_fail():
    with pytest.raises(ValueError, match="edition status"):
        summarize_sanction_coverage([state("158", "approved")], dated=False)
    with pytest.raises(ValueError, match="duplicate article"):
        summarize_sanction_coverage([state("158"), state("158")], dated=False)


def test_empty_reading_is_empty_coverage():
    coverage = summarize_sanction_coverage([], dated=True)
    assert coverage.total_articles == 0
    assert coverage.confirmed == coverage.unconfirmed == []
    assert all(keys == [] for keys in coverage.by_status.values())


def test_non_numeric_article_sorts_after_numbers():
    coverage = summarize_sanction_coverage([state("x-1"), state("158")], dated=False)
    assert coverage.unconfirmed == ["158", "x-1"]


def test_newest_readings_keep_first_reading_of_each_article():
    rows = [
        ("158", (2, "v2"), "a"),
        ("158", (2, "v2"), "b"),
        ("158", (2, "v1"), "old parser"),
        ("158", (1, "v2"), "old edition"),
        ("30", (1, "v1"), "c"),
    ]
    assert newest_readings(rows) == {"158": ["a", "b"], "30": ["c"]}


def test_newest_readings_keep_articles_in_given_order_and_handle_empty():
    rows = [("264.1", (1, "v"), 1), ("105", (1, "v"), 2)]
    assert list(newest_readings(rows)) == ["264.1", "105"]
    assert newest_readings([]) == {}


def test_newest_readings_reject_article_returning_after_another():
    rows = [("158", (1, "v"), 1), ("30", (1, "v"), 2), ("158", (1, "v"), 3)]
    with pytest.raises(ValueError, match="not grouped"):
        newest_readings(rows)
