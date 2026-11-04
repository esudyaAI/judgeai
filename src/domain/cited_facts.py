"""Cited observations and conservative merging, independent of models and persistence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CitedCandidate:
    path: tuple[str, ...]
    value: str | int | bool
    quote: str
    document_index: int
    document_hash: str
    start: int
    end: int


@dataclass(frozen=True)
class SegmentFacts:
    summary: str
    candidates: tuple[CitedCandidate, ...] = ()
    rejected: tuple[str, ...] = ()
    qualification: tuple[str, str] | None = None
    personality: str | None = None


@dataclass(frozen=True)
class MergedFacts:
    accepted: tuple[CitedCandidate, ...]
    conflicts: tuple[tuple[str, ...], ...]


def merge_candidates(candidates: tuple[CitedCandidate, ...]) -> MergedFacts:
    grouped: dict[tuple[str, ...], list[CitedCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.path, []).append(candidate)
    accepted, conflicts = [], []
    for path, items in grouped.items():
        # bool and int are distinct legal facts, even though Python considers True == 1.
        values = {(type(item.value), item.value) for item in items}
        if len(values) == 1:
            accepted.append(items[0])
        else:
            conflicts.append(path)
    return MergedFacts(tuple(accepted), tuple(conflicts))


def merge_segment_facts(readings: tuple[SegmentFacts, ...]) -> MergedFacts:
    merged = merge_candidates(tuple(c for reading in readings for c in reading.candidates))
    histories = [
        next((c.value for c in reading.candidates if c.path == ("history_complete",)), None)
        for reading in readings
    ]
    prior_problem = any(
        "prior_convictions" in path for reading in readings for path in reading.rejected
    ) or any(path[0] == "prior_convictions" for path in merged.conflicts)
    # Local completeness does not imply global completeness. Missing and conflicting
    # prior records must never become an assertion that there were no prior convictions.
    accepted = tuple(
        c
        for c in merged.accepted
        if not (
            c.path == ("history_complete",)
            and c.value is True
            and (not all(value is True for value in histories) or prior_problem)
        )
    )
    return MergedFacts(accepted, merged.conflicts)
