from src.schemas.analysis import LlmCaseFacts
from src.services.case_analyzer import assemble_analysis


def result(legal_facts=None, text="The offence was intentional."):
    facts = LlmCaseFacts.model_validate({"fabula": "Summary", "legal_facts": legal_facts})
    return assemble_analysis(
        facts,
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
    )


def test_missing_legal_inputs_are_not_a_clean_bill():
    checks = result().legal_checks
    assert {c.norm for c in checks} == {"ст. 15 УК РФ", "ст. 18 УК РФ"}
    assert all(c.status == "insufficient_data" and c.needs_legal_review for c in checks)


def test_fabricated_quote_cannot_support_a_category():
    checks = result(
        {
            "guilt": {"value": "intentional", "quote": "not in the document"},
            "sanction_max_months": {"value": 60, "quote": "not in the document"},
        }
    ).legal_checks
    assert checks[0].status == "insufficient_data"


def test_category_requires_the_statutory_ceiling_not_the_model():
    """The model no longer cites the sanction maximum: without the УК reading it is insufficient."""
    legal = {
        "guilt": {"value": "intentional", "quote": "intentional"},
        "sanction_max_months": {"value": 60, "quote": "60 months"},
        "harsher_than_imprisonment": {"value": False, "quote": "No life sentence"},
    }
    check = result(
        legal, text="An intentional offence. The sanction is 60 months. No life sentence."
    ).legal_checks[0]
    assert check.status == "insufficient_data"
    assert check.value is None


def test_empty_convictions_need_explicit_complete_history_evidence():
    legal = {
        "guilt": {"value": "intentional", "quote": "intentional"},
        "category": {"value": "medium", "quote": "medium"},
        "real_imprisonment": {"value": True, "quote": "real imprisonment"},
        "prior_convictions": [],
    }
    assert result(legal).legal_checks[1].status == "insufficient_data"


def test_complete_cited_history_can_support_no_recidivism():
    text = "intentional offence; medium gravity; real imprisonment; previously not convicted"
    legal = {
        "guilt": {"value": "intentional", "quote": "intentional offence"},
        "category": {"value": "medium", "quote": "medium gravity"},
        "real_imprisonment": {"value": True, "quote": "real imprisonment"},
        "history_complete": {"value": True, "quote": "previously not convicted"},
        "prior_convictions": [],
    }
    check = result(legal, text).legal_checks[1]
    assert check.status == "ok" and check.value == "none"
    assert check.needs_legal_review


def test_quote_outside_model_context_does_not_support_a_check():
    legal = {
        "guilt": {"value": "intentional", "quote": "intentional offence"},
        "sanction_max_months": {"value": 60, "quote": "60 months"},
        "harsher_than_imprisonment": {"value": False, "quote": "No life sentence"},
    }
    text = "A" * 40000 + " intentional offence; 60 months; No life sentence"
    assert result(legal, text).legal_checks[0].status == "insufficient_data"
