"""T15.6: сверка версии справки, сохранённой в результате анализа, с текущей.

Чистая логика без БД: на входе — версии из результата (T15.5) и текущие отпечатки справки
(T15.4), на выходе — изменилась ли справка после анализа и у каких замечаний сменилось
основание. Отсутствие сохранённой версии — «неизвестно», а не «совпадает».
"""

from src.domain.reference_drift import StoredCheck, compare_reference

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
