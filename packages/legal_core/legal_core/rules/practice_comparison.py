"""T28 — how a draft's term compares with the terms imposed in comparable precedents.

Pure arithmetic over precedent cards selected by the precedent search (filters and axes of
``precedent_matching``); it does not decide which precedents are comparable. The distribution
covers imprisonment terms in months, conditional ones included (their share is reported
separately). Quartiles use linear interpolation between order statistics (the "inclusive"
method of ``statistics.quantiles``). With fewer than MIN_PRECEDENTS terms the statistics are
returned but no position is given: a handful of verdicts is not practice.
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from legal_core.precedents import PrecedentCard

MIN_PRECEDENTS = 5


class Position(StrEnum):
    BELOW = "below"  # under the 25th percentile of comparable terms
    WITHIN = "within"  # inside the interquartile range, bounds included
    ABOVE = "above"  # over the 75th percentile


@dataclass(frozen=True)
class PracticeComparison:
    total: int  # precedents compared
    with_term: int  # of them, with a known imprisonment term
    min_months: float | None
    p25_months: float | None
    median_months: float | None
    p75_months: float | None
    max_months: float | None
    conditional_share: float | None
    art64_share: float | None
    art73_share: float | None
    draft_months: float | None
    draft_percentile: float | None  # mid-rank: share of terms below, plus half of equal ones
    position: Position | None

    @property
    def enough_data(self) -> bool:
        return self.with_term >= MIN_PRECEDENTS


def _share(cards: Sequence[PrecedentCard], predicate) -> float | None:
    if not cards:
        return None
    return round(sum(1 for c in cards if predicate(c)) / len(cards), 4)


def _quartiles(terms: list[float]) -> tuple[float, float, float]:
    if len(terms) == 1:
        return terms[0], terms[0], terms[0]
    p25, median, p75 = statistics.quantiles(terms, n=4, method="inclusive")
    return p25, median, p75


def compare_with_practice(
    precedents: Sequence[PrecedentCard], draft_months: float | None
) -> PracticeComparison:
    terms = sorted(m for c in precedents if (m := c.imprisonment_months) is not None)
    shares = (
        _share(precedents, lambda c: c.conditional),
        _share(precedents, lambda c: "64" in c.applied_general),
        _share(precedents, lambda c: "73" in c.applied_general),
    )
    if not terms:
        return PracticeComparison(
            len(precedents), 0, None, None, None, None, None, *shares, draft_months, None, None
        )
    p25, median, p75 = _quartiles(terms)
    percentile = position = None
    if draft_months is not None:
        below = sum(1 for t in terms if t < draft_months)
        equal = sum(1 for t in terms if t == draft_months)
        percentile = round((below + equal / 2) / len(terms) * 100, 1)
        if len(terms) >= MIN_PRECEDENTS:
            if draft_months < p25:
                position = Position.BELOW
            elif draft_months > p75:
                position = Position.ABOVE
            else:
                position = Position.WITHIN
    return PracticeComparison(
        total=len(precedents),
        with_term=len(terms),
        min_months=terms[0],
        p25_months=p25,
        median_months=median,
        p75_months=p75,
        max_months=terms[-1],
        conditional_share=shares[0],
        art64_share=shares[1],
        art73_share=shares[2],
        draft_months=draft_months,
        draft_percentile=percentile,
        position=position,
    )
