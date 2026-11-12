"""Versioned persistence adapter for the existing calculator; no DB/provider calls on replay.

Freezes per-subject prepared rule inputs for replay and human decisions. Legacy snapshots
retain their original decoding path. Assembly still mixes orchestration and presentation;
this adapter does not establish a fully reviewed clean-architecture boundary.
"""

import json
from dataclasses import fields, replace
from datetime import date, datetime
from enum import Enum
from typing import Literal

from legal_core.entities import ArticleReference, CountSentence, ImposedSentence, PunishmentTerm
from pydantic import BaseModel, ConfigDict, Field

from src.application.practice_report import PracticeReport
from src.domain.analysis_version import ANALYSIS_VERSION
from src.domain.prepared_legal import PreparedLegalInputs
from src.domain.prepared_sentencing import PreparedSentencingInputs
from src.domain.review_evidence import ReviewSources
from src.infrastructure.review_sources import load_review_sources, prepare_review_sources
from src.schemas.analysis import CaseAnalysis, ExtractionRead, LlmCaseFacts
from src.services.case_analyzer import (
    assemble_analysis,
    prepare_assembly_legal_inputs,
    prepare_assembly_sentencing_inputs,
)
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.legal_rule_catalog import ReferenceVersions


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _CountStatute(_StrictModel):
    reference: ArticleReference
    reading: StatuteSanctionReading


class _Arguments(_StrictModel):
    prompt: str
    documents: int
    pages: int
    seconds: int
    similar_items: list[dict]
    extra_warnings: list[str]
    document_texts: list[str] | None = None
    statute: StatuteSanctionReading | None = None
    sentence: ImposedSentence | None = None
    count_statutes: list[_CountStatute] = Field(default_factory=list)
    model_texts: list[str] | None = None
    extraction: ExtractionRead | None = None
    practice: PracticeReport | None = None
    precedent_source: str | None = None
    defendant_practice: dict[int, PracticeReport] | None = None
    prepared_legal_inputs: dict[int, PreparedLegalInputs] | None = None
    prepared_sentencing_inputs: dict[int, PreparedSentencingInputs] | None = None
    # T15.5/T15.11/T15.12: reference and sanction versions read when the analysis was made;
    # None — not recorded (snapshots stored before the port of T15).
    reference: ReferenceVersions | None = None


class _Snapshot(_StrictModel):
    contract_version: Literal[
        "calculation-inputs/1",
        "calculation-inputs/2",
        "calculation-inputs/3",
        "calculation-inputs/4",
    ] = "calculation-inputs/4"
    engine_version: str = ANALYSIS_VERSION
    facts: LlmCaseFacts
    kwargs: _Arguments
    provenance: dict | None = None
    review_sources: ReviewSources | None = None
    review_invalidations: list[Literal["practice"]] = Field(default_factory=list)
    review_practice_baseline: dict[int, PracticeReport] | None = None
    review_practice_refresh: dict | None = None


def _json_value(value):
    # Python-mode dumping retains sets; sort them before converting to JSON so
    # input hashes don't depend on process hash randomisation.
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, set | frozenset):
        return sorted((_json_value(item) for item in value), key=lambda item: json.dumps(item))
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def capture_inputs(facts: LlmCaseFacts, *, provenance: dict | None = None, **kwargs) -> dict:
    arguments = dict(kwargs)
    arguments["count_statutes"] = [
        {"reference": reference, "reading": reading}
        for reference, reading in sorted(
            (arguments.pop("count_statutes", None) or {}).items(),
            key=lambda pair: (pair[0].article, pair[0].part or 0),
        )
    ]
    parsed = _Arguments(**arguments)
    if parsed.prepared_legal_inputs is None:
        parsed.prepared_legal_inputs = prepare_assembly_legal_inputs(
            facts,
            prompt=parsed.prompt,
            document_texts=parsed.document_texts,
            model_texts=parsed.model_texts,
            extraction=parsed.extraction,
        )
    if parsed.prepared_sentencing_inputs is None:
        parsed.prepared_sentencing_inputs = prepare_assembly_sentencing_inputs(
            facts,
            document_texts=parsed.document_texts,
            sentence=parsed.sentence,
        )
    snapshot = _Snapshot(
        facts=facts,
        kwargs=parsed,
        provenance=provenance,
        review_sources=prepare_review_sources(parsed.document_texts, parsed.prompt),
    )
    # Roundtrip detaches all dictionaries/lists and refuses NaN/Infinity.
    return json.loads(json.dumps(_json_value(snapshot.model_dump(mode="python")), allow_nan=False))


def _restore_sentence_numbers(value, raw):
    """Retain integer vs fractional term amounts recorded by contract/3 preparation.

    Core terms accept either int or float, but the validation adapter normalises
    their float annotation. That must not rewrite saved explanatory text.
    """
    if isinstance(value, PunishmentTerm) and isinstance(raw, dict):
        amount = raw.get("amount")
        return replace(value, amount=amount) if type(amount) is int else value
    if isinstance(value, (ImposedSentence, CountSentence)) and isinstance(raw, dict):
        return replace(
            value,
            **{
                item.name: _restore_sentence_numbers(getattr(value, item.name), raw.get(item.name))
                for item in fields(value)
            },
        )
    if isinstance(value, tuple) and isinstance(raw, list):
        return tuple(
            _restore_sentence_numbers(item, source) for item, source in zip(value, raw, strict=True)
        )
    return value


def load_inputs(payload: dict) -> _Snapshot:
    snapshot = _Snapshot.model_validate(payload)
    if snapshot.engine_version != ANALYSIS_VERSION:
        raise ValueError("Saved calculation requires a different engine version")
    if (
        snapshot.contract_version != "calculation-inputs/1"
        and snapshot.kwargs.prepared_legal_inputs is None
    ):
        raise ValueError("Prepared legal inputs are missing")
    if (
        snapshot.contract_version in ("calculation-inputs/3", "calculation-inputs/4")
        and snapshot.kwargs.prepared_sentencing_inputs is None
    ):
        raise ValueError("Prepared sentencing inputs are missing")
    if snapshot.contract_version in ("calculation-inputs/3", "calculation-inputs/4"):
        raw_scopes = payload["kwargs"]["prepared_sentencing_inputs"]
        for index, prepared in snapshot.kwargs.prepared_sentencing_inputs.items():
            original = raw_scopes[str(index)] if str(index) in raw_scopes else raw_scopes[index]
            snapshot.kwargs.prepared_sentencing_inputs[index] = replace(
                prepared,
                sentence=_restore_sentence_numbers(prepared.sentence, original["sentence"]),
            )
    if snapshot.contract_version == "calculation-inputs/4":
        load_review_sources(payload)
    return snapshot


def replay_inputs(payload: dict) -> CaseAnalysis:
    snapshot = load_inputs(payload)
    arguments = {name: getattr(snapshot.kwargs, name) for name in _Arguments.model_fields}
    arguments["count_statutes"] = {
        item.reference: item.reading for item in snapshot.kwargs.count_statutes
    }
    if "practice" in snapshot.review_invalidations:
        arguments.update(
            practice=None, defendant_practice=None, similar_items=[], precedent_source=None
        )
    result = assemble_analysis(snapshot.facts, **arguments)
    result.provenance = snapshot.provenance
    return result
