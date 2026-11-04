"""Read every document window through a narrow extraction port before merging facts."""

from dataclasses import dataclass
from typing import Protocol

from src.domain.analysis_segments import AnalysisSegment, segment_documents
from src.domain.cited_facts import MergedFacts, SegmentFacts, merge_segment_facts
from src.domain.privacy import IdentifierSpan


class SegmentExtractor(Protocol):
    async def __call__(self, segment: AnalysisSegment) -> SegmentFacts: ...


@dataclass(frozen=True)
class SegmentedExtraction:
    segments: tuple[AnalysisSegment, ...]
    readings: tuple[SegmentFacts, ...]
    merged: MergedFacts


async def extract_document_segments(
    texts: list[str],
    extractor: SegmentExtractor,
    protected: tuple[tuple[IdentifierSpan, ...], ...] | None = None,
) -> SegmentedExtraction:
    segments = segment_documents(texts, protected=protected)
    readings = []
    for segment in segments:
        # A failed read propagates: the caller must not save a partial result as completed.
        readings.append(await extractor(segment))
    return SegmentedExtraction(segments, tuple(readings), merge_segment_facts(tuple(readings)))
