"""T15.6: сверка версии справки, сохранённой в результате анализа, с текущей.

Чистая логика без БД: на входе — версии из результата (T15.5) и текущие отпечатки справки
(T15.4), на выходе — изменилась ли справка после анализа и у каких замечаний сменилось
основание. Отсутствие сохранённой версии — «неизвестно», а не «совпадает».
"""

from src.domain.reference_drift import (
    StoredCheck,
    compare_article_versions,
    compare_reference,
    compare_version,
)

OLD = "sha256:" + "1" * 64
NEW = "sha256:" + "2" * 64
A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64


def test_same_catalog_is_current():
    drift = compare_reference(OLD, [StoredCheck("art15.category", A)], OLD, {"art15.category": A})
    assert drift.status == "current"
    assert drift.changed_rules == []
    assert [check.status for check in drift.checks] == ["current"]
    assert drift.checks[0].current_basis_version == A


def test_changed_basis_marks_the_finding_and_the_rule():
    drift = compare_reference(
        OLD,
        [StoredCheck("art15.category", A), StoredCheck("art18.recidivism", B)],
        NEW,
        {"art15.category": B, "art18.recidivism": B},
    )
    assert drift.status == "changed"
    assert drift.stored_version == OLD and drift.current_version == NEW
    assert [check.status for check in drift.checks] == ["changed", "current"]
    assert drift.changed_rules == ["art15.category"]


def test_catalog_changed_elsewhere_keeps_findings_current():
    # another rule's basis changed: the catalog moved, these findings did not
    drift = compare_reference(OLD, [StoredCheck("art15.category", A)], NEW, {"art15.category": A})
    assert drift.status == "changed"
    assert drift.checks[0].status == "current"
    assert drift.changed_rules == []


def test_result_without_recorded_version_is_unknown():
    checks = [StoredCheck("art15.category", None)]
    drift = compare_reference(None, checks, NEW, {"art15.category": A})
    assert drift.status == "unknown"
    assert drift.checks[0].status == "unknown"
    assert drift.changed_rules == []


def test_finding_without_rule_is_not_compared():
    drift = compare_reference(OLD, [StoredCheck(None, None)], OLD, {})
    assert drift.checks[0].status == "no_rule"
    assert drift.checks[0].current_basis_version is None


def test_rule_dropped_from_reference_is_a_change():
    drift = compare_reference(OLD, [StoredCheck("art15.category", A)], NEW, {})
    assert drift.checks[0].status == "changed"
    assert drift.checks[0].current_basis_version is None
    assert drift.changed_rules == ["art15.category"]


def test_changed_rules_are_unique_and_sorted():
    checks = [StoredCheck("b.rule", A), StoredCheck("a.rule", A), StoredCheck("b.rule", A)]
    drift = compare_reference(OLD, checks, NEW, {"a.rule": B, "b.rule": B})
    assert drift.changed_rules == ["a.rule", "b.rule"]
    assert [check.index for check in drift.checks] == [0, 1, 2]


# T15.11: одна сохранённая версия против текущей (версия данных санкций)


def test_same_version_is_current():
    drift = compare_version(OLD, OLD)
    assert drift.status == "current"
    assert drift.stored_version == OLD and drift.current_version == OLD


def test_other_version_is_changed():
    drift = compare_version(OLD, NEW)
    assert drift.status == "changed"
    assert drift.stored_version == OLD and drift.current_version == NEW


def test_missing_stored_version_is_unknown_not_current():
    drift = compare_version(None, NEW)
    assert drift.status == "unknown"
    assert drift.stored_version is None and drift.current_version == NEW


def test_reference_drift_without_sanctions_leaves_them_out():
    assert compare_reference(OLD, [], OLD, {}).sanctions is None


# T15.12 — per-article sanction versions


def test_article_versions_not_recorded_are_unknown():
    drift = compare_article_versions(None, {"158": A})
    assert drift.status == "unknown"
    assert drift.articles == []
    assert drift.changed_articles == []


def test_analysis_that_read_no_sanctions_is_current():
    drift = compare_article_versions({}, {"158": A})
    assert drift.status == "current"
    assert drift.articles == []


def test_same_article_versions_are_current_whatever_else_changed():
    drift = compare_article_versions({"158": A}, {"158": A, "159": B})
    assert drift.status == "current"
    assert [(d.article, d.status) for d in drift.articles] == [("158", "current")]
    assert drift.articles[0].current_version == A


def test_changed_and_removed_articles_are_reported_in_number_order():
    drift = compare_article_versions({"264.1": A, "30": A, "105": A}, {"264.1": B, "105": A})
    assert drift.status == "changed"
    assert [(d.article, d.status) for d in drift.articles] == [
        ("30", "removed"),
        ("105", "current"),
        ("264.1", "changed"),
    ]
    assert drift.articles[0].current_version is None
    assert drift.changed_articles == ["30", "264.1"]


def test_compare_reference_leaves_article_versions_uncompared():
    assert compare_reference(OLD, [], OLD, {}).sanction_articles is None
