"""Domain Layer — порядок версий парсера санкций (T15.14).

Версия парсера пишется как `<схема>/<номер>` (`statute-sanction-parser/2`). Новейший разбор
статьи выбирается по номеру внутри одной схемы, а не строковой сортировкой: для текста
«…/9» > «…/10». Если выбирать не из чего (одна версия), имя не проверяется. Если версий
несколько, но порядок между ними не определён (нет номера, разные схемы), — ошибка: конфликт
версий закрывается отказом, а не случайным выбором (DoD T23).
"""

import re
from collections.abc import Iterable

from src.domain.reference_conflict import ReferenceDataConflict

_VERSION = re.compile(r"(?P<scheme>[^/\s]+)/(?P<number>\d+)")


def parser_version_key(version: str) -> tuple[str, int]:
    """`statute-sanction-parser/10` → (`statute-sanction-parser`, 10)."""
    match = _VERSION.fullmatch(version)
    if match is None:
        raise ReferenceDataConflict(f"parser version without <scheme>/<number>: {version!r}")
    return match["scheme"], int(match["number"])


def newest_parser_version(versions: Iterable[str]) -> str:
    """The newest of the parser versions of one edition's reading of an article."""
    distinct = set(versions)
    if not distinct:
        raise ValueError("no parser versions")
    if len(distinct) == 1:
        return distinct.pop()
    keys = {version: parser_version_key(version) for version in distinct}
    schemes = {scheme for scheme, _ in keys.values()}
    if len(schemes) > 1:
        raise ReferenceDataConflict(f"parser versions of different schemes: {sorted(distinct)}")
    return max(distinct, key=lambda version: keys[version][1])
