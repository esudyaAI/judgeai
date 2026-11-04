"""Freeze subject attribution once; read original snapshot texts without current files/parsers."""

import json
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from src.application.review_evidence import RevisionSources
from src.domain.review_evidence import (
    InvalidEvidence,
    ReviewDocument,
    ReviewSources,
    SourceFingerprint,
    SourceRange,
    SubjectSource,
    validate_sources,
)
from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
from src.services.defendant_blocks import defendant_source_spans


def prepare_review_sources(document_texts, prompt) -> ReviewSources:
    documents = [ReviewDocument(index, "", text) for index, text in enumerate(document_texts or [])]
    if prompt:
        documents.append(ReviewDocument(-1, "", prompt))
    subjects = []
    for document in documents:
        if document.document_index < 0:
            continue
        for name, spans in defendant_source_spans(document.text):
            label = name.upper() if name.startswith("фио") else name.title()
            subjects.append(
                SubjectSource(
                    len(subjects),
                    label,
                    tuple(
                        SourceRange(document.document_index, start, end)
                        for start, end in spans
                        if end > start
                    ),
                )
            )
    if not subjects:
        subjects = [
            SubjectSource(
                0,
                "Лицо 1",
                tuple(
                    SourceRange(document.document_index, 0, len(document.text))
                    for document in documents
                    if document.text
                ),
            )
        ]
    context = ReviewSources(
        tuple(SourceFingerprint(doc.document_index, doc.document_hash) for doc in documents),
        tuple(subjects),
    )
    validate_sources(tuple(documents), context)
    return context


def load_review_sources(payload):
    if not isinstance(payload, dict) or payload.get("contract_version") != "calculation-inputs/4":
        raise InvalidEvidence("unsupported_snapshot")
    kwargs = payload.get("kwargs")
    if not isinstance(kwargs, dict):
        raise InvalidEvidence("invalid_context")
    texts, prompt = kwargs.get("document_texts"), kwargs.get("prompt")
    texts = [] if texts is None else texts
    if (
        not isinstance(texts, list)
        or any(type(text) is not str for text in texts)
        or type(prompt) is not str
    ):
        raise InvalidEvidence("invalid_context")
    extraction = kwargs.get("extraction") or {}
    if not isinstance(extraction, dict):
        raise InvalidEvidence("invalid_context")
    references = extraction.get("documents") or []
    if not isinstance(references, list) or any(
        not isinstance(item, dict)
        or type(item.get("document_index")) is not int
        or not 0 <= item["document_index"] < len(texts)
        for item in references
    ):
        raise InvalidEvidence("invalid_context")
    by_index = {item["document_index"]: item for item in references}
    if len(by_index) != len(references):
        raise InvalidEvidence("duplicate_document")
    documents = []
    for index, text in enumerate(texts):
        reference = by_index.get(index, {})
        document = ReviewDocument(index, reference.get("filename") or f"Материал {index + 1}", text)
        if reference.get("document_hash", document.document_hash) != document.document_hash:
            raise InvalidEvidence("documents_changed")
        documents.append(document)
    if prompt:
        documents.append(ReviewDocument(-1, "Вопрос пользователя", prompt))
    raw_context = payload.get("review_sources")
    if not isinstance(raw_context, dict) or set(raw_context) != {
        "version",
        "scoper_version",
        "offset_unit",
        "documents",
        "subjects",
    }:
        raise InvalidEvidence("invalid_context")
    try:
        context = TypeAdapter(ReviewSources).validate_json(
            json.dumps(raw_context, allow_nan=False), strict=True
        )
    except (ValidationError, TypeError, ValueError):
        raise InvalidEvidence("invalid_context") from None
    for key in ("prepared_legal_inputs", "prepared_sentencing_inputs"):
        mapping = kwargs.get(key)
        if not isinstance(mapping, dict) or {str(index) for index in mapping} != {
            str(person.subject_index) for person in context.subjects
        }:
            raise InvalidEvidence("invalid_subjects")
    validate_sources(tuple(documents), context)
    return tuple(documents), context


class SqlReviewSourceStore:
    def __init__(self, db):
        self.revisions = SqlAnalysisRevisionStore(db)

    async def source_context(self, owner_id, chat_id, message_id, revision_id):
        row = await self.revisions.get(owner_id, chat_id, message_id, UUID(revision_id))
        documents, context = load_review_sources(row.calculation_inputs)
        return RevisionSources(str(row.id), row.inputs_sha256, documents, context)
