"""Read-only, offline audit of every public verdict and every unextracted card field.

An empty extraction is a review task, never proof that a fact is absent in the verdict.
The report deliberately makes no automatic legal truth or recall claims.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from src.application.precedent_cards import MultiVerdictReader, build_cards
from src.domain.extraction import ExtractionMethod, input_hash
from src.domain.practice import PRIVATE_SOURCE_TYPES


@dataclass(frozen=True)
class AuditSource:
    key: str
    text: str
    source_type: str
    source_url: str | None = None
    input_error: str | None = None


@dataclass(frozen=True)
class FieldAudit:
    name: str
    status: str
    quote: str = ""


@dataclass(frozen=True)
class CardAudit:
    defendant_no: int
    version: str
    fields: tuple[FieldAudit, ...]


@dataclass(frozen=True)
class DocumentAudit:
    key: str
    source_url: str | None
    text_hash: str
    status: str
    cards: tuple[CardAudit, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class AuditReport:
    summary: dict[str, int]
    documents: tuple[DocumentAudit, ...]


def audit_source(
    reader: MultiVerdictReader, source: AuditSource, *, include_quotes: bool = False
) -> DocumentAudit:
    if source.source_type in PRIVATE_SOURCE_TYPES:
        return DocumentAudit(source.key, None, "", "skipped_private")
    if source.input_error:
        return DocumentAudit(source.key, None, "", "error", error=source.input_error)
    digest = input_hash(source.text)
    if not source.text.strip():
        return DocumentAudit(source.key, source.source_url, digest, "empty")
    try:
        extractions = build_cards(reader, source.text)
    except Exception as exc:
        # Exception messages may contain private text or connection parameters.
        return DocumentAudit(
            source.key, source.source_url, digest, "error", error=type(exc).__name__
        )
    if not extractions:
        return DocumentAudit(source.key, source.source_url, digest, "no_cards")
    cards = tuple(
        CardAudit(
            extraction.defendant_no,
            extraction.fields[0].extractor_version,
            tuple(
                FieldAudit(
                    field.name,
                    "needs_review" if field.method is ExtractionMethod.NONE else "present",
                    field.quote if include_quotes else "",
                )
                for field in extraction.fields
            ),
        )
        for extraction in extractions
    )
    return DocumentAudit(source.key, source.source_url, digest, "read", cards)


def audit_sources(
    reader: MultiVerdictReader, sources: Iterable[AuditSource], *, include_quotes: bool = False
) -> AuditReport:
    documents = tuple(
        audit_source(reader, source, include_quotes=include_quotes) for source in sources
    )
    counts = Counter(document.status for document in documents)
    summary = {
        name: counts[name] for name in ("read", "empty", "error", "no_cards", "skipped_private")
    }
    summary["errors"] = summary.pop("error")
    summary["sources"] = len(documents)
    summary["cards"] = sum(len(document.cards) for document in documents)
    for document in documents:
        for card in document.cards:
            for field in card.fields:
                if field.status == "needs_review":
                    name = f"missing:{field.name}"
                    summary[name] = summary.get(name, 0) + 1
    return AuditReport(summary, documents)
