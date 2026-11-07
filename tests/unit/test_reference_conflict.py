"""T15.16: конфликт справочных данных — отдельный тип отказа, а не любая ValueError.

Равенство дат получения редакций (T15.15) и несравнимые версии парсера (T15.14) — не ошибка
программы, а противоречие в данных: API отвечает на него «конфликт, проверка не выполнена»,
анализ — предупреждением. Для прежних вызывающих это по-прежнему ValueError.
"""

from datetime import UTC, datetime

import pytest

from src.domain.edition_order import newest_edition
from src.domain.parser_versions import newest_parser_version
from src.domain.reference_conflict import ReferenceDataConflict

MOMENT = datetime(2026, 10, 28, tzinfo=UTC)


def test_conflict_is_still_a_value_error():
    assert issubclass(ReferenceDataConflict, ValueError)


def test_editions_retrieved_at_one_moment_are_a_data_conflict():
    with pytest.raises(ReferenceDataConflict, match="same moment"):
        newest_edition([(1, MOMENT), (2, MOMENT)])


def test_unordered_parser_versions_are_a_data_conflict():
    with pytest.raises(ReferenceDataConflict, match="different schemes"):
        newest_parser_version(["a/1", "b/2"])
    with pytest.raises(ReferenceDataConflict, match="parser version"):
        newest_parser_version(["a/1", "unnumbered"])


def test_empty_input_is_a_programming_error_not_a_data_conflict():
    """Пустой вход вызывающий не передаёт: это ошибка кода, ответом 409 её не маскировать."""
    with pytest.raises(ValueError) as edition:
        newest_edition([])
    assert not isinstance(edition.value, ReferenceDataConflict)
    with pytest.raises(ValueError) as version:
        newest_parser_version([])
    assert not isinstance(version.value, ReferenceDataConflict)
