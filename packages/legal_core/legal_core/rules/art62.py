# Domain Layer — ч. 1 ст. 62 УК РФ «Назначение наказания при наличии смягчающих обстоятельств».
# With mitigating circumstances under п. «и» и (или) «к» ч. 1 ст. 61 and no aggravating
# circumstances, the term cannot exceed two thirds of the maximum of the most severe punishment
# in the sanction. Moved unchanged from src/services/sentencing.py (task T4); the text and the
# edition were not re-verified against the official source in this move.
# TODO(T4/T23): ч. 3 (no reduction for life imprisonment / death penalty), ч. 5 and the
# interplay with ст. 66 are not modelled; the caller passes the imprisonment maximum only.
import math
import re
from collections.abc import Iterable

NEEDS_LEGAL_REVIEW = True

_PART1_ART61 = re.compile(r"ч\.?\s*1\s*ст\.?\s*61(?!\d)(?!\.\d)", re.IGNORECASE)
_ITEM_LETTER = re.compile(r"«\s*([а-яё])\s*»", re.IGNORECASE)
_PART1_LETTERS = {"и", "к"}


def _cited_art61_part1_items(norm: str) -> set[str]:
    """Item letters of ч. 1 ст. 61 cited in a norm, e.g. 'п. «г», «и» ч. 1 ст. 61' -> {'г','и'}."""
    match = _PART1_ART61.search(norm)
    if not match:
        return set()
    return {letter.lower() for letter in _ITEM_LETTER.findall(norm[: match.start()])}


def has_part1_mitigation(mitigating_norms: Iterable[str]) -> bool:
    """Does any mitigating circumstance cite п. «и» or «к» ч. 1 ст. 61?"""
    return any(_cited_art61_part1_items(norm) & _PART1_LETTERS for norm in mitigating_norms)


def part1_limit_months(
    sanction_max_months: int, mitigating_norms: Iterable[str], *, has_aggravating: bool
) -> int | None:
    """Upper limit in whole months, or None when ч. 1 ст. 62 does not apply.

    Rounded down: rounding up could produce a term above the statutory two thirds.
    """
    if sanction_max_months <= 0 or has_aggravating:
        return None
    if not has_part1_mitigation(mitigating_norms):
        return None
    return math.floor(sanction_max_months * 2 / 3)


def part1_limit_amount(
    maximum: float, mitigating_norms: Iterable[str], *, has_aggravating: bool
) -> float | None:
    """Exact bound before expressing the punishment in days/hours/rubles; no monthly rounding."""
    from fractions import Fraction

    if maximum <= 0 or has_aggravating or not has_part1_mitigation(mitigating_norms):
        return None
    return Fraction(str(maximum)) * Fraction(2, 3)
