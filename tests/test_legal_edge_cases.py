"""Synthetic edge cases from T31–T37; never use private case material."""

from legal_core.entities import MeasureUnit, Unfinished

from src.infrastructure.verdict_reader import PracticeReader
from src.schemas.analysis import Circumstance, LlmCaseFacts
from src.services.case_analyzer import assemble_analysis
from src.services.punishment_extractor import extract_imposed_sentence
from src.services.regime_facts import read_male, read_served_before


def assemble(text, facts=None, **kwargs):
    return assemble_analysis(
        facts or LlmCaseFacts(fabula="Синтетика"),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        **kwargs,
    )


def test_negated_model_circumstance_never_reduces_sentence():
    text = "Явки с повинной как смягчающего обстоятельства суд не усматривает."
    facts = LlmCaseFacts(
        fabula="Синтетика",
        sanction_max_months=60,
        mitigating=[Circumstance(name="Явка с повинной", norm="п. «и» ч. 1 ст. 61")],
    )
    result = assemble(text, facts)
    assert result.mitigating == []
    assert result.scale.limit_months is None
    assert any("обстоятельств" in w for w in result.warnings)


def test_cited_but_negated_and_fabricated_circumstances_rejected():
    text = "Суд не признаёт явку с повинной смягчающим обстоятельством."
    facts = LlmCaseFacts(
        fabula="Синтетика",
        mitigating=[
            Circumstance.model_validate(
                {
                    "name": "Явка с повинной",
                    "norm": "п. «и» ч. 1 ст. 61",
                    "quote": "явку с повинной",
                }
            )
        ],
    )
    assert not assemble(text, facts).mitigating


def test_attempt_words_without_art30_and_conflicting_stage():
    text = (
        "ФИО1 признать виновным в покушении на грабёж по ч. 1 ст. 161 УК РФ "
        "и назначить наказание в виде лишения свободы на срок 2 года."
    )
    [count] = extract_imposed_sentence(text).sentence.counts
    assert count.unfinished is Unfinished.ATTEMPT
    conflict = text.replace("в покушении на грабёж", "в приготовлении к грабежу").replace(
        "по ч.", "по ч. 3 ст. 30, ч."
    )
    [count] = extract_imposed_sentence(conflict).sentence.counts
    assert count.stage_conflict is True


def test_personal_circumstances_not_copied_to_every_practice_card():
    text = (
        "ФИО1, ранее не судимый. ФИО2, ранее отбывал лишение свободы.\n"
        "УСТАНОВИЛ:\nСуд признаёт у ФИО1 смягчающим явку с повинной.\n\n"
        "У ФИО2 суд установил опасный рецидив преступлений.\nПРИГОВОРИЛ:\n"
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 1 год.\n"
        "ФИО2 признать виновным по ч. 2 ст. 161 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 4 года."
    )
    first, second = PracticeReader().read_all(text)
    assert "61.1.и" in first.mitigating and not second.mitigating
    assert first.recidivism.value == "none"
    assert second.recidivism.value == "dangerous"


def test_regime_facts_conflicting_sex_and_history_remain_unknown():
    assert read_male("Подсудимая. Подсудимый подсудимый подсудимый.")[0] is None
    assert (
        read_served_before("Ранее не отбывал лишение свободы. Отбывал лишение свободы.")[0] is None
    )
    assert read_served_before("Ранее отбывал реальное лишение свободы.")[0] is True


def test_intermediate_aggregate_and_unserved_are_preserved():
    text = (
        "ФИО1 назначить по ч. 1 ст. 158 УК РФ наказание в виде лишения свободы на срок 1 год.\n\n"
        "По ч. 3 ст. 69 УК РФ по совокупности назначить наказание в виде лишения свободы "
        "на срок 2 года.\n\nНеотбытый срок по прежнему "
        "приговору составляет 1 год лишения свободы.\n\n"
        "На основании ст. 70 УК РФ частично присоединить неотбытое наказание в виде "
        "3 месяцев лишения свободы и окончательно назначить наказание "
        "в виде лишения свободы на срок 2 года 3 месяца."
    )
    sentence = extract_imposed_sentence(text).sentence
    assert sentence.final.imprisonment_months == 27
    assert sentence.intermediate.imprisonment_months == 24
    assert sentence.unserved.imprisonment_months == 12
    assert sentence.joined.imprisonment_months == 3


def test_analysis_separates_people_and_does_not_use_global_model_facts():
    text = (
        "ФИО1, ранее не судимый. ФИО2, ранее отбывал лишение свободы.\n"
        "УСТАНОВИЛ:\nСуд признаёт у ФИО1 смягчающим явку с повинной.\n\n"
        "У ФИО2 суд установил опасный рецидив преступлений.\nПРИГОВОРИЛ:\n"
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 1 год.\n"
        "ФИО2 признать виновным по ч. 2 ст. 161 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 4 года."
    )
    result = assemble(
        text, LlmCaseFacts(fabula="Два осуждённых", sanction_max_months=60, recommended_months=12)
    )
    assert len(result.defendants) == 2
    assert not result.legal_checks and result.scale is None and not result.variants
    first, second = result.defendants
    assert first.mitigating and not second.mitigating
    assert (
        next(c for c in first.legal_checks if c.norm == "ст. 18 УК РФ").recidivism_input == "none"
    )
    assert (
        next(c for c in second.legal_checks if c.norm == "ст. 18 УК РФ").recidivism_input
        == "dangerous"
    )
    assert first.imposed_sentence.counts[0].imprisonment_months == 12
    assert second.imposed_sentence.counts[0].imprisonment_months == 48


def test_description_stage_and_ambiguous_repeated_article():
    operative = "По ч. 1 ст. 161 УК РФ назначить наказание в виде лишения свободы на срок 2 года."
    description = "Суд квалифицирует покушение на грабёж по ч. 1 ст. 161 УК РФ."
    assert (
        extract_imposed_sentence(operative, description).sentence.counts[0].unfinished
        is Unfinished.ATTEMPT
    )
    counts = extract_imposed_sentence(operative + "\n" + operative, description).sentence.counts
    assert all(c.stage_conflict for c in counts)


def test_different_people_interleaved_counts_remain_with_their_owner():
    text = (
        "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ.\n"
        "ФИО2 признать виновным по ч. 1 ст. 161 УК РФ.\n"
        "ФИО1 признать виновным по ч. 2 ст. 158 УК РФ."
    )
    from src.services.defendant_blocks import split_defendants

    first, second = split_defendants(text)
    assert "ч. 2 ст. 158" in first and "ч. 2 ст. 158" not in second


def test_empty_aggravating_list_is_not_a_proof_of_no_aggravation():
    text = "Суд признаёт явку с повинной смягчающим обстоятельством."
    facts = LlmCaseFacts(fabula="Синтетика", sanction_max_months=60)
    assert assemble(text, facts).scale.limit_months is None
    assert (
        assemble(text + " Отягчающих обстоятельств не установлено.", facts).scale.limit_months == 40
    )


def test_day_and_fractional_terms_are_not_truncated():
    from src.services.punishment_extractor import parse_term

    assert parse_term("1,5 года") == (18, MeasureUnit.MONTHS)
    assert parse_term("2 года 3 месяца 5 дней") == (815, MeasureUnit.DAYS)


def test_chronology_is_read_only_from_explicit_events_not_random_dates():
    from datetime import date

    from src.services.punishment_extractor import read_chronology

    operative = (
        "По ч. 1 ст. 158 УК РФ назначить наказание в виде лишения свободы на срок 1 год.\n\n"
        "По ч. 5 ст. 69 УК РФ по совокупности окончательно "
        "назначить лишение свободы на срок 2 года."
    )
    description = "Преступление по ч. 1 ст. 158 УК РФ совершено 01.01.2020."
    sentence = extract_imposed_sentence(operative, description).sentence
    assert sentence.counts[0].offence_date == date(2020, 1, 1)
    prior, _, credit, _ = read_chronology(
        "Прежний приговор от 02.02.2020. Зачесть отбытое "
        "наказание в виде лишения свободы на срок 6 месяцев."
    )
    assert prior == date(2020, 2, 2) and credit.imprisonment_months == 6
    assert read_chronology("Документ от 02.02.2020.")[0] is None


def test_collective_conviction_does_not_guess_individual_punishments():
    text = (
        "УСТАНОВИЛ:\nСуд рассматривает дело.\nПРИГОВОРИЛ:\n"
        "ФИО1 и ФИО2 признать виновными по ч. 1 ст. 158 УК РФ и назначить наказание "
        "в виде лишения свободы на срок 1 год."
    )
    result = assemble(text)
    assert len(result.defendants) == 2
    assert all(p.imposed_sentence is None for p in result.defendants)
    assert not result.legal_checks


def test_income_based_fine_is_not_compared_as_rubles_in_aggregate():
    from legal_core.entities import (
        ArticleReference,
        CountSentence,
        ImposedSentence,
        PunishmentKind,
        PunishmentTerm,
        SanctionRole,
        StatutorySanction,
    )

    from src.services.criminal_sanction_lookup import StatuteSanctionReading
    from tests.test_sentence_checks import PROVENANCE

    reference = ArticleReference("999", 1)
    count = CountSentence(
        "ч. 1 ст. 999 УК РФ",
        reference,
        PunishmentTerm(PunishmentKind.FINE, 10000, MeasureUnit.RUBLES),
    )
    # A sanction in months of income cannot become a fixed number of rubles.
    reading = StatuteSanctionReading(
        sanctions=[
            StatutorySanction(
                "999",
                1,
                PunishmentKind.FINE,
                SanctionRole.MAIN,
                None,
                6,
                MeasureUnit.MONTHS,
                "доход за шесть месяцев",
            )
        ],
        provenance=PROVENANCE,
    )
    result = assemble(
        "Синтетический приговор",
        sentence=ImposedSentence(
            counts=(count, count),
            final=PunishmentTerm(PunishmentKind.FINE, 15000, MeasureUnit.RUBLES),
            aggregation_rule="ч. 2 ст. 69 УК РФ",
        ),
        count_statutes={reference: reading},
    )
    final = next(c for c in result.legal_checks if c.norm.startswith("Окончательное наказание"))
    assert final.status == "insufficient_data"


def test_practice_reports_of_repeated_pseudonyms_use_stable_person_index():
    from unittest.mock import patch

    from src.services import case_analyzer
    from tests.test_multidefendant_analysis import TEXT

    # Two uploaded documents can both use ФИО1/ФИО2 for different people.
    original = case_analyzer.assemble_analysis
    own_calls = []

    def own(facts, **kwargs):
        own_calls.append(kwargs.get("practice"))
        # The marker is for routing only, no actual practice query is run.
        kwargs["practice"] = None
        return original(facts, **kwargs)

    markers = {i: object() for i in range(4)}
    with patch.object(case_analyzer, "assemble_analysis", side_effect=own):
        result = original(
            LlmCaseFacts(fabula="Синтетика"),
            prompt="",
            documents=2,
            pages=2,
            seconds=1,
            similar_items=[],
            extra_warnings=[],
            document_texts=[TEXT, TEXT],
            defendant_practice=markers,
        )
    assert len(result.defendants) == 4 and own_calls == list(markers.values())


def test_personal_quotes_are_literal_source_fragments_without_synthetic_headings():
    from tests.test_multidefendant_analysis import TEXT

    result = assemble(TEXT)
    for person in result.defendants:
        for circumstance in person.mitigating:
            assert circumstance.quote in TEXT
        for check in person.legal_checks:
            for quote in check.evidence:
                assert quote in TEXT
