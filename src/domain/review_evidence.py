"""Exact provenance and subject-scope validation; no legal inference or external adapters."""

import re
from dataclasses import dataclass, field

from src.domain.extraction import input_hash


class InvalidEvidence(ValueError):
    pass


@dataclass(frozen=True)
class ReviewDocument:
    document_index: int
    filename: str
    text: str
    document_hash: str = field(init=False)

    def __post_init__(self):
        if (
            type(self.document_index) is not int
            or self.document_index < -1
            or type(self.text) is not str
        ):
            raise InvalidEvidence("invalid_document")
        object.__setattr__(self, "document_hash", input_hash(self.text))


@dataclass(frozen=True)
class SourceFingerprint:
    document_index: int
    document_hash: str

    def __post_init__(self):
        if type(self.document_index) is not int or self.document_index < -1:
            raise InvalidEvidence("invalid_document")
        if not isinstance(self.document_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.document_hash
        ):
            raise InvalidEvidence("invalid_hash")


@dataclass(frozen=True)
class SourceRange:
    document_index: int
    start: int
    end: int

    def __post_init__(self):
        if any(type(value) is not int for value in (self.document_index, self.start, self.end)):
            raise InvalidEvidence("invalid_coordinates")
        if self.document_index < -1 or self.start < 0 or self.end <= self.start:
            raise InvalidEvidence("invalid_coordinates")


@dataclass(frozen=True)
class SubjectSource:
    subject_index: int
    label: str
    ranges: tuple[SourceRange, ...]

    def __post_init__(self):
        if type(self.subject_index) is not int or self.subject_index < 0:
            raise InvalidEvidence("invalid_subject")
        if not isinstance(self.label, str) or not self.label.strip():
            raise InvalidEvidence("invalid_subject")


@dataclass(frozen=True)
class ReviewSources:
    documents: tuple[SourceFingerprint, ...]
    subjects: tuple[SubjectSource, ...]
    version: str = "review-sources/1"
    scoper_version: str = "defendant-source-ranges/1"
    offset_unit: str = "unicode-codepoint"

    def __post_init__(self):
        if self.version != "review-sources/1" or self.offset_unit != "unicode-codepoint":
            raise InvalidEvidence("unsupported_context")
        if not isinstance(self.scoper_version, str) or not self.scoper_version.strip():
            raise InvalidEvidence("unsupported_context")
        indexes = [doc.document_index for doc in self.documents]
        if len(set(indexes)) != len(indexes):
            raise InvalidEvidence("duplicate_document")
        if [person.subject_index for person in self.subjects] != list(range(len(self.subjects))):
            raise InvalidEvidence("invalid_subjects")
        if not self.subjects:
            raise InvalidEvidence("invalid_subjects")
        for person in self.subjects:
            if any(span.document_index not in indexes for span in person.ranges):
                raise InvalidEvidence("invalid_document")


@dataclass(frozen=True)
class Evidence:
    document_index: int
    document_hash: str
    start: int
    end: int
    quote: str


def validate_sources(documents: tuple[ReviewDocument, ...], context: ReviewSources) -> None:
    actual = {doc.document_index: doc for doc in documents}
    if len(actual) != len(documents) or set(actual) != {
        doc.document_index for doc in context.documents
    }:
        raise InvalidEvidence("documents_changed")
    if any(
        actual[item.document_index].document_hash != item.document_hash
        for item in context.documents
    ):
        raise InvalidEvidence("documents_changed")
    for person in context.subjects:
        if any(span.end > len(actual[span.document_index].text) for span in person.ranges):
            raise InvalidEvidence("invalid_coordinates")


def validate_evidence(
    documents: tuple[ReviewDocument, ...],
    context: ReviewSources,
    subject_index: int,
    evidence: Evidence,
) -> None:
    validate_sources(documents, context)
    if type(subject_index) is not int or not 0 <= subject_index < len(context.subjects):
        raise InvalidEvidence("invalid_subject")
    if any(
        type(value) is not int for value in (evidence.document_index, evidence.start, evidence.end)
    ):
        raise InvalidEvidence("invalid_coordinates")
    document = next(
        (doc for doc in documents if doc.document_index == evidence.document_index), None
    )
    if document is None or evidence.document_hash != document.document_hash:
        raise InvalidEvidence("documents_changed")
    if not 0 <= evidence.start < evidence.end <= len(document.text):
        raise InvalidEvidence("invalid_coordinates")
    if (
        not isinstance(evidence.quote, str)
        or not evidence.quote.strip()
        or len(evidence.quote) > 4000
    ):
        raise InvalidEvidence("invalid_quote")
    if document.text[evidence.start : evidence.end] != evidence.quote:
        raise InvalidEvidence("quote_mismatch")
    if not any(
        span.document_index == evidence.document_index
        and span.start <= evidence.start
        and evidence.end <= span.end
        for span in context.subjects[subject_index].ranges
    ):
        raise InvalidEvidence("wrong_subject")
