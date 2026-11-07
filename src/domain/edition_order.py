"""Domain Layer — выбор новейшей редакции статьи по `retrieved_at` (T15.15).

Новейший разбор санкций статьи берётся из редакции с самой поздней датой получения
(`retrieved_at`). Если эту дату делят две разные редакции, порядок между ними не определён:
прежде его молча решал порядок строк БД, и анализ, справка и версии санкций могли опираться на
любую из них. Такой конфликт редакций закрывается отказом, а не случайным выбором (DoD T23).
Одинаковая дата у более старых редакций не мешает — выбирается только новейшая.
"""

from collections.abc import Hashable, Iterable
from typing import Any, TypeVar

E = TypeVar("E", bound=Hashable)


def newest_edition(editions: Iterable[tuple[E, Any]]) -> E:
    """The edition with the latest `retrieved_at` among `(edition, retrieved_at)` pairs.

    Pairs may repeat (one per sanction row). Two distinct editions sharing the latest moment
    are refused with ValueError.
    """
    moments: dict[E, Any] = {}
    for edition, moment in editions:
        moments.setdefault(edition, moment)
    if not moments:
        raise ValueError("no editions")
    latest = max(moments.values())
    newest = [edition for edition, moment in moments.items() if moment == latest]
    if len(newest) > 1:
        raise ValueError(f"editions retrieved at the same moment: {sorted(newest, key=str)}")
    return newest[0]
