"""T15.15: новейшая редакция статьи — по `retrieved_at`, равенство дат — отказ.

Прежде две редакции с одной датой получения упорядочивал порядок строк БД: анализ и справка
могли молча опираться на любую из них. Теперь такой конфликт — ошибка, а не случайный выбор.
"""

from datetime import UTC, datetime

import pytest

from src.domain.edition_order import newest_edition

OLD = datetime(2026, 10, 28, tzinfo=UTC)
NEW = datetime(2026, 11, 1, tzinfo=UTC)


def test_latest_retrieved_edition_wins_whatever_the_input_order():
    assert newest_edition([(1, OLD), (2, NEW)]) == 2
    assert newest_edition([(2, NEW), (1, OLD)]) == 2


def test_repeated_rows_of_one_edition_are_one_edition():
    assert newest_edition([(7, NEW), (7, NEW), (7, NEW)]) == 7


def test_two_editions_retrieved_at_the_same_moment_are_refused():
    with pytest.raises(ValueError, match="same moment: \\[3, 5\\]"):
        newest_edition([(5, NEW), (3, NEW), (1, OLD)])


def test_tie_between_older_editions_does_not_matter():
    assert newest_edition([(1, OLD), (2, OLD), (3, NEW)]) == 3


def test_no_editions_is_an_error():
    with pytest.raises(ValueError, match="no editions"):
        newest_edition([])
