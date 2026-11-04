"""Apply detected and explicitly reviewed spans; keep their correspondence locally."""

import re
from dataclasses import dataclass
from typing import Protocol

from src.domain.privacy import IdentifierSpan, PrivacyRejected, PseudonymSession


class IdentifierDetector(Protocol):
    def __call__(self, text: str) -> tuple[IdentifierSpan, ...]: ...


@dataclass(frozen=True)
class AnonymizedTexts:
    texts: tuple[str, ...]
    session: PseudonymSession


def identifier_spans(
    texts: tuple[str, ...], detector: IdentifierDetector, known_values: tuple[str, ...] = ()
) -> tuple[tuple[IdentifierSpan, ...], ...]:
    detected = [detector(text) for text in texts]
    if sum(map(len, detected)) > 20000:
        raise PrivacyRejected("Слишком много идентификаторов для одного запроса.")
    # A name found next to a procedural role must also be masked when repeated elsewhere.
    known = set(known_values) | {
        text[span.start : span.end]
        for text, spans in zip(texts, detected, strict=True)
        for span in spans
    }
    pattern = (
        re.compile(
            "|".join(
                re.sub("[еёЕЁ]", "[её]", re.escape(value))
                for value in sorted(known, key=len, reverse=True)
            ),
            re.IGNORECASE,
        )
        if known
        else None
    )
    result = []
    for text, spans in zip(texts, detected, strict=True):
        repeated = (
            tuple(IdentifierSpan(m.start(), m.end()) for m in pattern.finditer(text))
            if pattern
            else ()
        )
        if len(spans) + len(repeated) > 40000:
            raise PrivacyRejected("Слишком много идентификаторов для одного запроса.")
        result.append((*spans, *repeated))
    return tuple(result)


def anonymize_texts(
    texts: tuple[str, ...],
    detector: IdentifierDetector,
    nonce: str,
    known_values: tuple[str, ...] = (),
) -> AnonymizedTexts:
    spans = identifier_spans(texts, detector, known_values)
    session = PseudonymSession(nonce)
    masked = tuple(session.mask(text, own) for text, own in zip(texts, spans, strict=True))
    return AnonymizedTexts(masked, session)


@dataclass(frozen=True)
class ExpandedFragment:
    matched: bool
    text: str | None


def expand_source_fragment(
    fragment: str,
    sources: tuple[str, ...],
    spans: tuple[tuple[IdentifierSpan, ...], ...],
    max_chars: int = 30000,
) -> ExpandedFragment:
    """Expand a raw source window so a detected identifier is never cut at its edge.

    Ambiguous origins or oversized fields are refused. Formatted prompts, which are not
    literal source fragments, are handled by their source-aware segmentation upstream.
    """
    if not fragment:
        return ExpandedFragment(False, None)
    candidates, matches = set(), 0
    for source, own in zip(sources, spans, strict=True):
        offset = source.find(fragment)
        while offset >= 0:
            matches += 1
            if matches > 100:
                return ExpandedFragment(True, None)
            start, end = offset, offset + len(fragment)
            while any(s.start < start < s.end or s.start < end < s.end for s in own):
                crossing = [s for s in own if s.start < start < s.end or s.start < end < s.end]
                start = min(start, *(s.start for s in crossing))
                end = max(end, *(s.end for s in crossing))
            if end - start > max_chars:
                return ExpandedFragment(True, None)
            candidates.add(source[start:end])
            if len(candidates) > 1:
                return ExpandedFragment(True, None)
            offset = source.find(fragment, offset + 1)
    return ExpandedFragment(bool(matches), next(iter(candidates)) if candidates else None)
