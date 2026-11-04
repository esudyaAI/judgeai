import pytest
from legal_core.entities import SanctionCeiling

from src.domain.prepared_legal import PreparedFact, PreparedLegalInputs, evaluate_legal_inputs
from src.schemas.analysis import CitedFact, LegalFacts
from src.services.legal_checks import build_legal_checks, prepare_legal_inputs


def fact(value, quote="Точная цитата из источника"):
    return PreparedFact(value, quote)


def test_category_uses_prepared_guilt_and_the_existing_core_rule():
    prepared = PreparedLegalInputs(category_guilt=fact("intentional"))
    result = evaluate_legal_inputs(prepared, SanctionCeiling(120))
    assert result.category == "grave"
    assert result.category_evidence == ("Точная цитата из источника",)
    assert result.recidivism is None


@pytest.mark.parametrize("value", [0, 1, 1.0, [], {}])
def test_prepared_facts_reject_non_boolean_numbers_and_containers(value):
    with pytest.raises(ValueError):
        PreparedFact(value, "Точная цитата")


def test_missing_history_does_not_mean_no_prior_convictions():
    common = dict(
        model_guilt=fact("intentional"), category=fact("grave"), real_imprisonment=fact(True)
    )
    assert evaluate_legal_inputs(PreparedLegalInputs(**common)).recidivism is None
    assert (
        evaluate_legal_inputs(
            PreparedLegalInputs(**common, history_complete=fact(False))
        ).recidivism
        is None
    )
    assert (
        evaluate_legal_inputs(PreparedLegalInputs(**common, history_complete=fact(True))).recidivism
        == "none"
    )


def test_preparation_keeps_invalid_model_guilt_from_using_regex_fallback():
    text = "Суд установил умышленное преступление."
    candidate = LegalFacts(guilt=CitedFact(value="intentional", quote="Несуществующая цитата"))
    prepared = prepare_legal_inputs(
        candidate, text, text_guilt=CitedFact(value="intentional", quote="умышленное преступление")
    )
    assert evaluate_legal_inputs(prepared, SanctionCeiling(120)).category is None


def test_explicit_prepared_values_are_not_overwritten_by_raw_model_or_regex():
    text = "В источнике умышленное деяние, а проверяющий уточняет форму вины."
    raw = LegalFacts(guilt=CitedFact(value="intentional", quote="умышленное деяние"))
    prepared = PreparedLegalInputs(category_guilt=fact("negligent"))
    checks = build_legal_checks(raw, text, SanctionCeiling(120), prepared=prepared)
    assert checks[0].value == "medium"
    assert checks[0].evidence == ["Точная цитата из источника"]
