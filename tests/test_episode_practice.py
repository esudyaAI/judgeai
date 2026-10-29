"""Synthetic application regressions; no database, provider or private verdicts."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification, Recidivism

from src.application.practice_report import compare_draft_with_practice
from src.application.similar_precedents import SimilarPrecedent, SimilarPrecedents, StoredCard
from src.services.legal_checks import build_legal_checks


def term(months):
    return PunishmentTerm(PunishmentKind.IMPRISONMENT, months, MeasureUnit.MONTHS)


def card(episodes, recidivism=Recidivism.DANGEROUS, final=None):
    return PrecedentCard(
        tuple(episodes), frozenset(), frozenset(), recidivism, frozenset(), final, False, ""
    )


def item(n, value):
    stored = StoredCard(n, value, n, None, None, None, None)
    return SimilarPrecedent(stored, 1, {}, (), 1, (), None)


@pytest.mark.asyncio
async def test_each_count_is_searched_and_compared_without_aggregate(monkeypatch):
    theft = PrecedentEpisode(Qualification("158", 2), term(24))
    robbery = PrecedentEpisode(Qualification("162", 2), term(60))
    draft = card([theft, robbery], final=term(72))
    candidates = [
        item(1, card([replace(theft, punishment=term(18)), robbery], final=term(80))),
        item(2, card([theft], recidivism=Recidivism.NONE)),
        item(3, card([theft], recidivism=None)),
    ]
    search = AsyncMock(
        side_effect=[
            SimilarPrecedents(candidates, 3, 0, False),
            SimilarPrecedents([candidates[0]], 1, 0, False),
        ]
    )
    monkeypatch.setattr("src.application.practice_report.FindSimilarPrecedents.execute", search)
    report = await compare_draft_with_practice(None, None, draft)
    assert [call.args[0].main_qualification.article for call in search.call_args_list] == [
        "158",
        "162",
    ]
    assert report.comparison.draft_months is None
    assert [r.comparison.draft_months for r in report.episodes] == [24, 60]
    assert [r.comparison.median_months for r in report.episodes] == [18, 60]
    assert report.episodes[0].comparison.with_term == 1
    assert len(report.shown) == 3


@pytest.mark.asyncio
async def test_ambiguous_counts_do_not_use_final(monkeypatch):
    theft = PrecedentEpisode(Qualification("158", 2), None)
    candidate = item(1, card([theft, theft], final=term(72)))
    search = AsyncMock(return_value=SimilarPrecedents([candidate], 1, 0, False))
    monkeypatch.setattr("src.application.practice_report.FindSimilarPrecedents.execute", search)
    report = await compare_draft_with_practice(None, None, card([theft]))
    assert report.comparison.with_term == 0
    assert report.comparison.draft_months is None


def test_extracted_recidivism_is_evidence_not_verified_classification():
    quote = "Суд установил опасный рецидив преступлений."
    checks = build_legal_checks(
        None, quote, extracted_recidivism=Recidivism.DANGEROUS, recidivism_quote=quote
    )
    for check in checks[1:]:
        assert check.status == "insufficient_data"
        assert "опасный" in check.value
        assert check.evidence == [quote]
    assert checks[-1].norm == "ст. 58 УК РФ"
    assert (
        len(
            build_legal_checks(
                None, "", extracted_recidivism=Recidivism.DANGEROUS, recidivism_quote=quote
            )
        )
        == 2
    )


def test_assembly_exposes_episodes_and_cleans_model_labels():
    from legal_core.rules.practice_comparison import compare_with_practice

    from src.application.practice_report import PracticeReport
    from src.schemas.analysis import LlmCaseFacts, PunishmentVariant
    from src.services.case_analyzer import assemble_analysis

    episode = PrecedentEpisode(Qualification("158", 2), term(24))
    query = card([episode])
    comparison = compare_with_practice([], 24)
    single = PracticeReport(query, [], 0, 0, False, comparison)
    report = replace(single, episodes=[single])
    facts = LlmCaseFacts(
        fabula="Синтетический пример",
        variants=[
            PunishmentVariant(
                label="final_sentence",
                title="final_sentence",
                details="final_sentence",
                rationale="final_sentence",
            )
        ],
    )
    quote = "Суд установил опасный рецидив преступлений."
    result = assemble_analysis(
        facts,
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[quote],
        model_texts=["Сокращённый текст."],
        practice=report,
    )
    assert result.practice_episodes[0].draft_months == 24
    assert result.practice_episodes[0].recidivism == "dangerous"
    assert "final_sentence" not in result.variants[0].model_dump_json()
    assert result.legal_checks[-1].evidence == [quote]


@pytest.mark.asyncio
async def test_second_article_is_not_hidden_by_first_articles_results(monkeypatch):
    theft = PrecedentEpisode(Qualification("158", 2), term(24))
    robbery = PrecedentEpisode(Qualification("162", 2), term(60))
    first = [item(n, card([theft])) for n in range(1, 21)]
    second = item(100, card([robbery]))
    search = AsyncMock(
        side_effect=[
            SimilarPrecedents(first, 20, 0, False),
            SimilarPrecedents([second], 1, 0, False),
        ]
    )
    monkeypatch.setattr("src.application.practice_report.FindSimilarPrecedents.execute", search)
    report = await compare_draft_with_practice(None, None, card([theft, robbery]))
    assert len(report.shown) == 10
    assert report.shown[1].stored.id == 100


def test_text_and_calculated_recidivism_conflict_requires_review():
    from src.schemas.analysis import LegalFacts

    quote = "Суд установил опасный рецидив преступлений."
    text = (
        "intentional offence; medium gravity; real imprisonment; previously not convicted. " + quote
    )
    facts = LegalFacts.model_validate(
        {
            "guilt": {"value": "intentional", "quote": "intentional offence"},
            "category": {"value": "medium", "quote": "medium gravity"},
            "real_imprisonment": {"value": True, "quote": "real imprisonment"},
            "history_complete": {"value": True, "quote": "previously not convicted"},
        }
    )
    check = build_legal_checks(
        facts, text, extracted_recidivism=Recidivism.DANGEROUS, recidivism_quote=quote
    )[1]
    assert check.status == "insufficient_data"
    assert "расходится" in check.explanation
    assert "расчёт: none" in check.value
