"""Lossless model-sized windows with coordinates in the original document.

Overlap keeps citations at a window boundary readable. Coordinates are Unicode character
indices (end exclusive), never offsets into a normalized or shortened model context.
"""

from dataclasses import dataclass

from src.domain.extraction import input_hash
from src.domain.privacy import IdentifierSpan, PrivacyRejected

MODEL_DOCUMENT_CHARS = 30000
SEGMENT_CHARS = 28000
SEGMENT_OVERLAP = 2000


@dataclass(frozen=True)
class AnalysisSegment:
    document_index: int
    document_hash: str
    start: int
    end: int
    text: str


def segment_documents(
    texts: list[str],
    *,
    max_chars: int = SEGMENT_CHARS,
    overlap: int = SEGMENT_OVERLAP,
    protected: tuple[tuple[IdentifierSpan, ...], ...] | None = None,
) -> tuple[AnalysisSegment, ...]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("segment limit must be positive and overlap smaller than the limit")
    if protected is not None and len(protected) != len(texts):
        raise ValueError("protected spans must correspond to every document")
    segments = []
    for document_index, text in enumerate(texts):
        if not text.strip():
            continue
        spans = protected[document_index] if protected is not None else ()
        for span in spans:
            if (
                not 0 <= span.start < span.end <= len(text)
                or span.end - span.start > max_chars - overlap
            ):
                raise PrivacyRejected("identifier cannot fit in a protected model window")
        digest = input_hash(text)
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            while any(s.start < end < s.end for s in spans):
                end = min(s.start for s in spans if s.start < end < s.end)
            if end <= start:
                raise PrivacyRejected("cannot split a protected model window")
            segments.append(AnalysisSegment(document_index, digest, start, end, text[start:end]))
            if end == len(text):
                break
            next_start = end - overlap
            while any(s.start < next_start < s.end for s in spans):
                next_start = min(s.start for s in spans if s.start < next_start < s.end)
            if next_start <= start:
                raise PrivacyRejected("protected overlap cannot make progress")
            start = next_start
    return tuple(segments)
