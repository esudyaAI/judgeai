"""Comparing a draft (query card) with a precedent card: filters, axes and rank fusion.

Filters are tri-state: missing data is UNCERTAIN, never a failure. What a failed filter does
(exclude, lower the score, or only inform) is configuration. The score is a weighted sum of
the axes that have data; weights are renormalised over them, and the per-axis breakdown is
returned as the explanation of the match.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from legal_core.precedents import PrecedentCard, Qualification


class FilterState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class FilterAction(StrEnum):
    EXCLUDE = "exclude"
    SCORE = "score"
    INFO = "info"


@dataclass(frozen=True)
class FilterResult:
    name: str
    state: FilterState
    reason: str
    action: FilterAction


def _default_actions() -> dict[str, FilterAction]:
    return {
        "same_article": FilterAction.EXCLUDE,
        "same_part": FilterAction.SCORE,
        "same_recidivism": FilterAction.SCORE,
    }


def _default_weights() -> dict[str, float]:
    return {"qualification": 0.35, "circumstances": 0.30, "recidivism": 0.20, "text": 0.15}


def _default_circumstance_weights() -> dict[str, float]:
    # Circumstances that change the limits of punishment weigh more than the rest:
    # п. «и», «к» ч. 1 ст. 61 (ч. 1 ст. 62) and every aggravating circumstance of ст. 63.
    return {"61.1.и": 2.0, "61.1.к": 2.0, "63": 2.0}


@dataclass(frozen=True)
class MatchConfig:
    weights: dict[str, float] = field(default_factory=_default_weights)
    actions: dict[str, FilterAction] = field(default_factory=_default_actions)
    circumstance_weights: dict[str, float] = field(default_factory=_default_circumstance_weights)
    same_part_score: float = 0.85
    same_article_score: float = 0.5
    other_part_cap: float = 0.6
    failed_filter_penalty: float = 0.8

    def action(self, name: str) -> FilterAction:
        return self.actions.get(name, FilterAction.INFO)

    def circumstance_weight(self, code: str) -> float:
        if code in self.circumstance_weights:
            return self.circumstance_weights[code]
        return self.circumstance_weights.get(code.split(".")[0], 1.0)


@dataclass(frozen=True)
class MatchResult:
    excluded: bool
    score: float
    breakdown: dict[str, dict[str, float]]
    filters: tuple[FilterResult, ...]


def _matching_qualifications(
    query: PrecedentCard, candidate: PrecedentCard
) -> tuple[Qualification | None, Qualification | None]:
    """Use the best shared composition, irrespective of source episode order.

    Unknown parts take precedence over a proven mismatch: an unrelated count cannot
    turn an unparsed part of the matching article into a confirmed different part.
    Punishment amounts never participate in selecting a comparable composition.
    """
    pairs = [
        (q.qualification, c.qualification)
        for q in query.episodes
        for c in candidate.episodes
        if q.qualification.article == c.qualification.article
    ]
    if not pairs:
        return query.main_qualification, candidate.main_qualification
    return max(
        pairs,
        key=lambda pair: (
            pair[0] == pair[1],
            pair[0].part is not None and pair[0].part == pair[1].part,
            pair[0].part is None or pair[1].part is None,
            pair[0].key,
            pair[1].key,
        ),
    )


def hard_filters(
    query: PrecedentCard, candidate: PrecedentCard, config: MatchConfig
) -> tuple[FilterResult, ...]:
    def result(name: str, state: FilterState, reason: str) -> FilterResult:
        return FilterResult(name, state, reason, config.action(name))

    q_main, c_main = _matching_qualifications(query, candidate)
    out = []
    if q_main is None or c_main is None:
        out.append(result("same_article", FilterState.UNCERTAIN, "квалификация не извлечена"))
    else:
        q_articles = {e.qualification.article for e in query.episodes}
        c_articles = {e.qualification.article for e in candidate.episodes}
        common = q_articles & c_articles
        if common:
            out.append(result("same_article", FilterState.PASSED, f"ст. {min(common)}"))
        else:
            out.append(
                result(
                    "same_article",
                    FilterState.FAILED,
                    f"другая статья: ст. {', '.join(sorted(c_articles))}",
                )
            )
    if q_main is None or c_main is None or q_main.part is None or c_main.part is None:
        out.append(result("same_part", FilterState.UNCERTAIN, "часть статьи не указана"))
    elif (q_main.article, q_main.part) == (c_main.article, c_main.part):
        out.append(result("same_part", FilterState.PASSED, f"ч. {q_main.part}"))
    else:
        out.append(result("same_part", FilterState.FAILED, f"другая часть: {c_main}"))
    if query.recidivism is None or candidate.recidivism is None:
        out.append(result("same_recidivism", FilterState.UNCERTAIN, "нет данных о рецидиве"))
    elif query.recidivism is candidate.recidivism:
        out.append(result("same_recidivism", FilterState.PASSED, query.recidivism.value))
    else:
        out.append(
            result("same_recidivism", FilterState.FAILED, f"рецидив: {candidate.recidivism.value}")
        )
    return tuple(out)


def _qualification_axis(
    query: PrecedentCard, candidate: PrecedentCard, config: MatchConfig
) -> float | None:
    q, c = _matching_qualifications(query, candidate)
    if q is None or c is None:
        return None
    if query.qualification_keys & candidate.qualification_keys:
        return 1.0
    if q.article == c.article and q.part == c.part:
        return config.same_part_score
    if {e.qualification.article for e in query.episodes} & {
        e.qualification.article for e in candidate.episodes
    }:
        return config.same_article_score
    return 0.0


def _circumstances_axis(
    query: PrecedentCard, candidate: PrecedentCard, config: MatchConfig
) -> float | None:
    q = query.mitigating | query.aggravating
    c = candidate.mitigating | candidate.aggravating
    union = q | c
    if not union:
        return None
    weight = config.circumstance_weight
    return sum(weight(code) for code in q & c) / sum(weight(code) for code in union)


def _recidivism_axis(query: PrecedentCard, candidate: PrecedentCard) -> float | None:
    if query.recidivism is None or candidate.recidivism is None:
        return None
    return 1.0 if query.recidivism is candidate.recidivism else 0.0


def evaluate_candidate(
    query: PrecedentCard,
    candidate: PrecedentCard,
    text_similarity: float | None,
    config: MatchConfig,
) -> MatchResult:
    filters = hard_filters(query, candidate, config)
    excluded = any(
        f.state is FilterState.FAILED and f.action is FilterAction.EXCLUDE for f in filters
    )
    axes = {
        "qualification": _qualification_axis(query, candidate, config),
        "circumstances": _circumstances_axis(query, candidate, config),
        "recidivism": _recidivism_axis(query, candidate),
        "text": None if text_similarity is None else min(1.0, max(0.0, text_similarity)),
    }
    present = {name: value for name, value in axes.items() if value is not None}
    total_weight = sum(config.weights.get(name, 0.0) for name in present)
    breakdown: dict[str, dict[str, float]] = {}
    score = 0.0
    if total_weight > 0:
        for name, value in present.items():
            weight = config.weights.get(name, 0.0) / total_weight
            breakdown[name] = {"score": round(value, 4), "weight": weight}
            score += value * weight
    for f in filters:
        if f.state is FilterState.FAILED and f.action is FilterAction.SCORE:
            score *= config.failed_filter_penalty
    part_filter = next(f for f in filters if f.name == "same_part")
    if part_filter.state is FilterState.FAILED:
        score = min(score, config.other_part_cap)
    return MatchResult(excluded, round(score, 4), breakdown, filters)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[Hashable]], k: int = 60
) -> list[tuple[Hashable, float]]:
    """Merges ranked lists: each item gets sum(1 / (k + rank)), rank starting at 1."""
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], str(pair[0])))
