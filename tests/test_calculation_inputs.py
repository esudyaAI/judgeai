"""Frozen calculator inputs must preserve real outputs, including subject attribution."""

import json

import pytest
from legal_core.entities import ArticleReference

from src.infrastructure.calculation_inputs import capture_inputs, replay_inputs
from src.schemas.analysis import LlmCaseFacts
from src.services.case_analyzer import assemble_analysis
from src.services.verdict_structure import read_verdict_structure
from tests.test_multidefendant_analysis import TEXT
from tests.test_statute_sanction_analysis import PART_2


@pytest.mark.parametrize(
    "text",
    [
        "Подсудимый действовал умышленно. Назначить 3 года лишения свободы.",
        TEXT,
        "",
    ],
)
def test_roundtrip_replays_the_same_checks_and_personal_attribution(text):
    facts = LlmCaseFacts(fabula="Синтетический результат", sanction_max_months=48)
    kwargs = dict(
        prompt="Проверь",
        documents=1,
        pages=2,
        seconds=3,
        similar_items=[],
        extra_warnings=["Сохранённое ограничение"],
        document_texts=[text],
        sentence=read_verdict_structure([text], 30000).sentence,
        statute=PART_2,
        count_statutes={ArticleReference("158", 2): PART_2},
    )
    expected = assemble_analysis(facts, **kwargs).model_dump(mode="json")
    snapshot = capture_inputs(facts, **kwargs)
    persisted = json.loads(json.dumps(snapshot, ensure_ascii=False))
    assert replay_inputs(persisted).model_dump(mode="json") == expected
    assert persisted["kwargs"]["count_statutes"][0]["reference"] == {"article": "158", "part": 2}
    assert persisted["kwargs"]["statute"]["provenance"]["source_sha256"] == "0" * 64


def test_snapshot_is_independent_from_later_mutation_of_materials_and_statutes():
    from copy import deepcopy

    statute = deepcopy(PART_2)
    facts = LlmCaseFacts(fabula="Изначальная сводка")
    kwargs = dict(
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=["Изначальный материал"],
        statute=statute,
    )
    snapshot = capture_inputs(facts, **kwargs)
    before = replay_inputs(snapshot).model_dump(mode="json")
    facts.fabula = "Изменено"
    kwargs["document_texts"][0] = "Заменено"
    statute.sanctions.clear()
    assert replay_inputs(snapshot).model_dump(mode="json") == before


def test_unsupported_engine_or_contract_is_rejected_instead_of_using_current_rules():
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=0,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
    )
    for change in ({"engine_version": "future"}, {"contract_version": "unknown"}):
        with pytest.raises(ValueError):
            replay_inputs({**snapshot, **change})


def test_populated_sentence_dates_units_fine_and_practice_survive_replay():
    from dataclasses import replace
    from datetime import date

    from legal_core.precedents import PrecedentEpisode, Qualification
    from legal_core.rules.practice_comparison import compare_with_practice

    from src.application.practice_report import PracticeReport
    from tests.test_episode_practice import card, item, term

    text = (
        "Подсудимый действовал умышленно.\nПРИГОВОРИЛ:\n"
        "По ч. 2 ст. 158 УК РФ назначить наказание в виде лишения свободы на срок 2 года."
    )
    sentence = read_verdict_structure([text], 30000).sentence
    assert sentence.counts
    sentence = replace(sentence, prior_judgment_date=date(2024, 2, 29))
    query = card([PrecedentEpisode(Qualification("158", 2), term(24))])
    candidate = item(1, query)
    candidate = replace(candidate, stored=replace(candidate.stored, decision_date=date(2023, 1, 1)))
    report = PracticeReport(
        query,
        [candidate],
        1,
        0,
        False,
        compare_with_practice([query], 24),
        candidate_pool=[candidate],
    )
    facts = LlmCaseFacts(fabula="Синтетические материалы")
    kwargs = dict(
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        sentence=sentence,
        statute=PART_2,
        count_statutes={ArticleReference("158", 2): PART_2},
        practice=report,
        defendant_practice={1: report},
    )
    snapshot = capture_inputs(facts, **kwargs)
    assert snapshot["kwargs"]["sentence"]["prior_judgment_date"] == "2024-02-29"
    assert (
        snapshot["kwargs"]["practice"]["candidate_pool"][0]["stored"]["decision_date"]
        == "2023-01-01"
    )
    assert replay_inputs(snapshot).model_dump(mode="json") == assemble_analysis(
        facts, **kwargs
    ).model_dump(mode="json")


async def test_snapshot_keeps_statistics_candidates_beyond_the_ten_shown(monkeypatch):
    from unittest.mock import AsyncMock

    from legal_core.precedents import PrecedentEpisode, Qualification

    from src.application.practice_report import compare_draft_with_practice
    from src.application.similar_precedents import SimilarPrecedents
    from tests.test_episode_practice import card, item, term

    query = card([PrecedentEpisode(Qualification("158", 2), term(24))])
    candidates = [item(number, query) for number in range(1, 17)]
    monkeypatch.setattr(
        "src.application.practice_report.FindSimilarPrecedents.execute",
        AsyncMock(return_value=SimilarPrecedents(candidates, 16, 0, False)),
    )
    practice = await compare_draft_with_practice(None, None, query)
    assert len(practice.shown) == 10 and practice.episodes[0].comparison.with_term == 16
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=0,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        practice=practice,
    )
    assert len(snapshot["kwargs"]["practice"]["shown"]) == 10
    assert len(snapshot["kwargs"]["practice"]["candidate_pool"]) == 16
    assert replay_inputs(snapshot).practice_episodes[0].with_term == 16


@pytest.mark.parametrize("version", ["calculation-inputs/1", "calculation-inputs/2"])
def test_old_input_contract_without_prepared_values_still_replays_identically(version):
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=["Подсудимый действовал умышленно."],
        statute=PART_2,
    )
    expected = replay_inputs(snapshot).model_dump(mode="json")
    legacy = json.loads(json.dumps(snapshot))
    legacy["contract_version"] = version
    legacy["kwargs"].pop("prepared_sentencing_inputs")
    if version == "calculation-inputs/1":
        legacy["kwargs"].pop("prepared_legal_inputs")
    assert replay_inputs(legacy).model_dump(mode="json") == expected


def test_explicit_unknown_is_not_recreated_from_original_text():
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=["Подсудимый действовал умышленно."],
        statute=PART_2,
    )
    initial = next(
        check for check in replay_inputs(snapshot).legal_checks if check.norm == "ст. 15 УК РФ"
    )
    assert initial.value == "medium"
    snapshot["kwargs"]["prepared_legal_inputs"]["0"]["category_guilt"] = {
        "value": None,
        "quote": "",
    }
    checks = replay_inputs(snapshot).legal_checks
    category = next(check for check in checks if check.norm == "ст. 15 УК РФ")
    assert category.status == "insufficient_data" and category.value is None


def test_prepared_personal_inputs_remain_separate_and_require_all_subjects():
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[TEXT],
    )
    prepared = snapshot["kwargs"]["prepared_legal_inputs"]
    assert prepared["0"]["stated_recidivism"] == "none"
    assert prepared["1"]["stated_recidivism"] == "dangerous"
    prepared["1"]["stated_recidivism"], prepared["1"]["stated_quote"] = None, ""
    people = replay_inputs(snapshot).defendants
    first = next(check for check in people[0].legal_checks if check.norm == "ст. 18 УК РФ")
    second = next(check for check in people[1].legal_checks if check.norm == "ст. 18 УК РФ")
    assert first.recidivism_input == "none" and second.recidivism_input is None
    prepared.pop("1")
    with pytest.raises(ValueError, match="subjects"):
        replay_inputs(snapshot)


def test_snapshot_cannot_turn_an_integer_into_a_prepared_boolean():
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=0,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
    )
    snapshot["kwargs"]["prepared_legal_inputs"]["0"]["real_imprisonment"] = {
        "value": 1,
        "quote": "synthetic",
    }
    with pytest.raises(ValueError):
        replay_inputs(snapshot)


def test_prior_boolean_fields_survive_prepared_input_serialization():
    from src.schemas.analysis import CitedFact, LegalFacts

    quote = "Синтетический источник сведений о судимости"

    def cited(value):
        return CitedFact(value=value, quote=quote)

    prior = dict(
        judgment_id="synthetic-prior",
        guilt="intentional",
        category="grave",
        adult_at_offence=True,
        active_at_offence=True,
        convicted_before_offence=True,
        imprisoned_by_sentence=True,
        conditional_or_deferred=False,
        revoked_and_sent_before_offence=False,
    )
    legal = LegalFacts(
        guilt=cited("intentional"),
        category=cited("grave"),
        real_imprisonment=cited(True),
        history_complete=cited(True),
        prior_convictions=[{name: cited(value) for name, value in prior.items()}],
    )
    snapshot = capture_inputs(
        LlmCaseFacts(fabula="synthetic", legal_facts=legal),
        prompt="",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[quote],
    )
    assert snapshot["contract_version"] == "calculation-inputs/4"
    prepared_prior = snapshot["kwargs"]["prepared_legal_inputs"]["0"]["prior_convictions"][0]
    flags = {name: field["value"] for name, field in prepared_prior}
    assert flags["conditional_or_deferred"] is False and flags["active_at_offence"] is True
    result = replay_inputs(json.loads(json.dumps(snapshot)))
    assert (
        next(check for check in result.legal_checks if check.norm == "ст. 18 УК РФ").value
        == "dangerous"
    )
