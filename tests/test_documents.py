from src.schemas.analysis import LlmCaseFacts
from src.services.case_analyzer import assemble_analysis, build_user_prompt
from src.services.knowledge_service import build_chunks


def test_long_paragraph_keeps_the_end():
    text = "A" * 6000 + "TAIL_MARKER"
    chunks = build_chunks(text)
    assert "".join(chunks) == text
    assert all(len(chunk) <= 2500 for chunk in chunks)


def test_chunk_limit_does_not_silently_discard_text():
    text = "B" * 25001
    assert "".join(build_chunks(text)) == text


def test_document_beyond_old_limit_reaches_model():
    prompt = build_user_prompt("Check", ["A" * 6000 + "TAIL_MARKER"], [])
    assert "TAIL_MARKER" in prompt


def test_context_overflow_is_visible_in_result():
    result = assemble_analysis(
        LlmCaseFacts(fabula="Summary"),
        prompt="Check",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=["A" * 40000],
    )
    assert any("не полностью" in warning.lower() for warning in result.warnings)


def test_negative_model_terms_are_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LlmCaseFacts(fabula="Summary", sanction_max_months=-1)
    with pytest.raises(ValidationError):
        LlmCaseFacts(fabula="Summary", recommended_months=-1)
