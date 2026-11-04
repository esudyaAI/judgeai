from dataclasses import replace

from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import Recidivism

from src.domain.prepared_legal import PreparedFact
from src.domain.prepared_sentencing import evaluate_regime_inputs
from src.services.regime_facts import prepare_regime_inputs

TEXT = "Подсудимый ранее не отбывал лишение свободы; исправительная колония общего режима."


def test_prepared_regime_preserves_boolean_false_and_calls_existing_rule():
    inputs = prepare_regime_inputs(TEXT)
    assert inputs.male.value is True and inputs.served_before.value is False
    result = evaluate_regime_inputs(inputs, Recidivism.NONE, Category.GRAVE, Guilt.INTENTIONAL)
    assert result.status.value == "ok"


def test_cleared_prepared_sex_does_not_get_inferred_from_source_again():
    inputs = replace(prepare_regime_inputs(TEXT), male=PreparedFact())
    result = evaluate_regime_inputs(inputs, Recidivism.NONE, Category.GRAVE, Guilt.INTENTIONAL)
    assert result.status.value == "insufficient_data"
    assert "пол осуждённого" in result.explanation


def test_unknown_previously_stated_regime_is_reported_as_insufficient():
    inputs = replace(prepare_regime_inputs(TEXT), imposed=PreparedFact())
    result = evaluate_regime_inputs(inputs, Recidivism.NONE, Category.GRAVE, Guilt.INTENTIONAL)
    assert result.status.value == "insufficient_data"
    assert "назначенный вид учреждения" in result.explanation


def snapshot(text, *, sentence=None, **extra):
    from src.infrastructure.calculation_inputs import capture_inputs
    from src.schemas.analysis import LlmCaseFacts

    return capture_inputs(
        LlmCaseFacts(fabula="synthetic", **extra),
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        sentence=sentence,
    )


def test_snapshot_does_not_restore_removed_circumstances_or_absence_flag():
    from src.infrastructure.calculation_inputs import replay_inputs

    text = (
        "Суд признаёт явку с повинной смягчающим обстоятельством. "
        "Отягчающих обстоятельств не установлено."
    )
    saved = snapshot(text, sanction_max_months=48)
    prepared = saved["kwargs"]["prepared_sentencing_inputs"]["0"]
    assert prepared["mitigating"] and prepared["no_aggravating"]["value"] is True
    assert replay_inputs(saved).scale.limit_months == 32
    prepared["no_aggravating"] = {"value": None, "quote": ""}
    assert replay_inputs(saved).scale.limit_months is None
    prepared["mitigating"] = []
    assert replay_inputs(saved).mitigating == []


def test_snapshot_does_not_restore_cleared_prior_date_and_unserved_term():
    from src.infrastructure.calculation_inputs import replay_inputs
    from src.services.verdict_structure import read_verdict_structure
    from tests.test_prior_terms import _INTRO_BARE_BALANCE, _OPERATIVE_JOINED_BARE

    text = (
        "Прежний приговор от 10.01.2020.\n"
        + _INTRO_BARE_BALANCE
        + "\nУСТАНОВИЛ:\nsynthetic\nПРИГОВОРИЛ:\n"
        + _OPERATIVE_JOINED_BARE
    )
    sentence = read_verdict_structure([text], 30000).sentence
    saved = snapshot(text, sentence=sentence)
    prepared = saved["kwargs"]["prepared_sentencing_inputs"]["0"]["sentence"]
    assert prepared["unserved"] is not None
    assert prepared["prior_judgment_date"] == "2020-01-10"
    prepared["unserved"], prepared["unserved_quote"] = None, ""
    prepared["prior_judgment_date"], prepared["prior_judgment_quote"] = None, ""
    result = replay_inputs(saved)
    assert result.imposed_sentence.unserved is None
    assert result.imposed_sentence.prior_judgment_date is None


def test_saved_exception_is_authoritative_even_when_original_quote_still_names_art64():
    from src.schemas.analysis import LlmCaseFacts
    from src.services.case_analyzer import prepare_assembly_sentencing_inputs
    from src.services.sentence_checks import build_sentence_checks
    from tests.test_sentence_checks import REF, _reading, _recidivism, _sentence

    sentence = _sentence(months=6, quote="С применением ст. 64 УК РФ лишение свободы")
    prepared = prepare_assembly_sentencing_inputs(
        LlmCaseFacts(fabula="synthetic"),
        document_texts=[sentence.counts[0].quote],
        sentence=sentence,
    )[0]
    assert prepared.art64_by_count[0].value is True
    [initial] = build_sentence_checks(
        sentence, {REF: _reading()}, _recidivism(), [], prepared=prepared
    )
    assert initial.status == "ok"
    cleared = replace(prepared, art64_by_count=(PreparedFact(),))
    [changed] = build_sentence_checks(
        sentence, {REF: _reading()}, _recidivism(), [], prepared=cleared
    )
    assert changed.status == "possible_violation"


def test_current_contract_requires_a_complete_sentencing_map():
    import pytest

    from src.infrastructure.calculation_inputs import replay_inputs

    saved = snapshot(TEXT)
    saved["kwargs"].pop("prepared_sentencing_inputs")
    with pytest.raises(ValueError, match="missing"):
        replay_inputs(saved)
    saved["kwargs"]["prepared_sentencing_inputs"] = {}
    with pytest.raises(ValueError, match="subjects"):
        replay_inputs(saved)
