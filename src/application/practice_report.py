"""Use case: precedents comparable to a draft and the draft's place among their terms (T28).

The search decides comparability (channels, filters, axes); the comparison only counts terms
of what the search kept. A wider pool than the list shown is used for the statistics, so the
distribution is not limited to the first screen of results.
"""

from dataclasses import dataclass, field, replace

from legal_core.precedents import PrecedentCard
from legal_core.rules.practice_comparison import PracticeComparison, compare_with_practice

from src.application.similar_precedents import (
    EmbeddingPort,
    FindSimilarPrecedents,
    PrecedentStore,
    SimilarPrecedent,
)

SHOWN = 10
STATISTICS_POOL = 50


@dataclass(frozen=True)
class PracticeReport:
    query: PrecedentCard
    shown: list[SimilarPrecedent]
    candidates: int
    excluded: int
    vector_used: bool
    comparison: PracticeComparison
    episodes: list["PracticeReport"] = field(default_factory=list)


async def compare_draft_with_practice(
    store: PrecedentStore, embedder: EmbeddingPort, query: PrecedentCard
) -> PracticeReport:
    # Search each count separately: the first article must not hide another composition.
    reports = []
    for episode in query.episodes:
        single = replace(query, episodes=(episode,), final=None)
        found = await FindSimilarPrecedents(store, embedder).execute(single, STATISTICS_POOL)
        comparable = []
        for item in found.items:
            card = item.stored.card
            # Unknown recidivism is not evidence of the same recidivism.
            if query.recidivism is not None and card.recidivism != query.recidivism:
                continue
            matches = [e for e in card.episodes if e.qualification == episode.qualification]
            # Multiple matching counts are ambiguous; never substitute the aggregate term.
            if len(matches) != 1:
                continue
            match = matches[0]
            term = match.punishment
            if term is None and len(card.episodes) == 1:
                term = card.final
            comparable.append(
                replace(card, episodes=(replace(match, punishment=term),), final=None)
            )
        reports.append(
            PracticeReport(
                single,
                found.items[:SHOWN],
                found.candidates,
                found.excluded + len(found.items) - len(comparable),
                found.vector_used,
                compare_with_practice(comparable, single.imprisonment_months),
            )
        )
    shown = {}
    for rank in range(SHOWN):
        for report in reports:
            if rank < len(report.shown):
                item = report.shown[rank]
                shown.setdefault(item.stored.id, item)
    # No aggregate comparison for a multi-count draft. The legacy field stays readable.
    comparison = reports[0].comparison if len(reports) == 1 else compare_with_practice([], None)
    return PracticeReport(
        query,
        list(shown.values())[:SHOWN],
        sum(r.candidates for r in reports),
        sum(r.excluded for r in reports),
        any(r.vector_used for r in reports),
        comparison,
        reports,
    )
