"""Domain Layer — охват санкций по статьям УК в справке (T15.9).

Сводка по статьям, у которых в БД разобраны санкции (`criminal_article_sanctions`): чья
санкция опирается на сверенную редакцию, действовавшую на дату, а чья — на несверенную,
отклонённую, недействовавшую или редакцию с неизвестным периодом. Чистая логика без
фреймворков и БД: состояние статьи (статус сверки редакции и действие нормы на дату)
приходит из запроса к БД, здесь оно только классифицируется. Ни одна статья не пропадает,
неизвестный статус сверки — ошибка, а не молчаливый пропуск.
"""

import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from typing import TypeVar

SANCTION_STATUSES: tuple[str, ...] = (
    "verified",
    "period_unknown",
    "unreviewed",
    "outdated",
    "rejected",
)
EDITION_STATUSES = frozenset({"unreviewed", "verified", "rejected"})
CONFIRMED = "verified"
_ARTICLE_NUMBER = re.compile(r"\d+(?:\.\d+)*")

T = TypeVar("T")


@dataclass(frozen=True)
class ArticleSanctionState:
    """Санкции статьи в новейшей разобранной редакции.

    `in_force` — действовала ли норма на запрошенную дату (None — период неизвестен или
    дата не запрошена); без даты не учитывается.
    """

    article: str
    edition_status: str
    in_force: bool | None = None


@dataclass(frozen=True)
class SanctionCoverage:
    total_articles: int
    by_status: dict[str, list[str]]
    confirmed: list[str]
    unconfirmed: list[str]


def article_status(state: ArticleSanctionState, *, dated: bool) -> str:
    """Статус санкции статьи; на дату недействовавшая норма — `outdated` при любой сверке."""
    if state.edition_status not in EDITION_STATUSES:
        raise ValueError(f"unknown edition status: {state.edition_status}")
    if dated and state.in_force is False:
        return "outdated"
    if state.edition_status != CONFIRMED:
        return state.edition_status
    if dated and state.in_force is None:
        return "period_unknown"
    return CONFIRMED


def article_sort_key(article: str) -> tuple:
    """Номера статей по числу (30 < 105 < 264 < 264.1), прочее — после, по тексту."""
    if _ARTICLE_NUMBER.fullmatch(article):
        return (0, tuple(int(part) for part in article.split(".")), article)
    return (1, (), article)


def summarize_sanction_coverage(
    states: list[ArticleSanctionState], *, dated: bool
) -> SanctionCoverage:
    """Group articles by sanction status; every status is present, articles sorted by number."""
    by_status: dict[str, list[str]] = {status: [] for status in SANCTION_STATUSES}
    seen: set[str] = set()
    for state in states:
        status = article_status(state, dated=dated)
        if state.article in seen:
            raise ValueError(f"duplicate article: {state.article}")
        seen.add(state.article)
        by_status[status].append(state.article)
    for articles in by_status.values():
        articles.sort(key=article_sort_key)
    confirmed = list(by_status[CONFIRMED])
    return SanctionCoverage(
        total_articles=len(seen),
        by_status=by_status,
        confirmed=confirmed,
        unconfirmed=sorted(seen - set(confirmed), key=article_sort_key),
    )


def newest_readings(rows: Iterable[tuple[str, Hashable, T]]) -> dict[str, list[T]]:
    """T15.10: per article, the items of its newest reading only.

    `rows` are `(article, reading, item)` grouped by article, each group newest reading first
    (the order of the database query); `reading` identifies one reading of an article (edition
    and parser version). Items of older readings are dropped; an article that comes back after
    another one means the input is not grouped — an error, not a silent merge.
    """
    found: dict[str, list[T]] = {}
    newest: dict[str, Hashable] = {}
    previous: str | None = None
    for article, reading, item in rows:
        if article != previous and article in found:
            raise ValueError(f"rows are not grouped by article: {article}")
        previous = article
        if article not in found:
            found[article], newest[article] = [], reading
        if reading == newest[article]:
            found[article].append(item)
    return found
