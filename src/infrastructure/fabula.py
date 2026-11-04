"""Adapter: the plot of the crime (fabula) from the descriptive part of a verdict.

The fabula ends where the court turns to the evidence or to the defendant's position.
Without such a marker the beginning of the descriptive part is used.
"""

import re

from src.application.anonymization import identifier_spans
from src.infrastructure.identifier_detector import detect_identifiers

MAX_FABULA_CHARS = 3000
_EVIDENCE_START = re.compile(
    r"(?:В\s+судебном\s+заседании|Вина\s+подсудим|Виновность\s+подсудим|Допрошенн"
    r"|Исследовав\s+(?:представленные\s+)?доказательства|Подсудим\w+\s+[^.]{0,80}вину"
    r"|Суд\s+квалифицирует|Действия\s+подсудим)",
)


def extract_fabula(description: str, *, materials: tuple[str, ...] = ()) -> str:
    text = description.strip()
    match = _EVIDENCE_START.search(text)
    if match and match.start() > 0:
        text = text[: match.start()]
    end = min(len(text), MAX_FABULA_CHARS)
    spans = identifier_spans((text, *materials), detect_identifiers)[0]
    while any(span.start < end < span.end for span in spans):
        end = min(span.start for span in spans if span.start < end < span.end)
    return text[:end].strip()
