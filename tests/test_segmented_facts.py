"""Synthetic model results prove full coverage, provenance and conservative merging."""

import pytest

from src.schemas.analysis import CitedFact, LegalFacts, LlmCaseFacts
from src.services.segmented_facts import extract_case_segments


def facts(value=None, quote="точная цитата"):
    return LlmCaseFacts(
        fabula="Описание фрагмента",
        legal_facts=LegalFacts(guilt=CitedFact(value=value, quote=quote)) if value else None,
    )


async def test_long_document_tail_reaches_extractor_and_keeps_coordinates():
    text = "начало " + "а" * 60000 + " умышленное преступление"
    seen = []

    async def reader(llm, question, texts, similar):
        seen.extend(texts)
        return (
            facts("intentional", "умышленное преступление") if "умышленное" in texts[0] else facts()
        )

    result = await extract_case_segments(None, "Проверь", [text], [], window_reader=reader)
    assert len(seen) == 3 and all(len(t) <= 28000 for t in seen)
    assert result.facts.legal_facts.guilt.value == "intentional"
    assert result.extraction.complete
    cited = next(f for f in result.extraction.facts if f.path == ["guilt"])
    assert text[cited.start : cited.end] == cited.quote
    assert cited.document_index == 0
    assert not result.extraction.conflicts


async def test_contradictory_segment_facts_are_not_chosen_arbitrarily():
    texts = ["умышленное преступление " + "а" * 32000, "неосторожное преступление"]

    async def reader(llm, question, windows, similar):
        if "умышленное" in windows[0]:
            return facts("intentional", "умышленное преступление")
        if "неосторожное" in windows[0]:
            return facts("negligent", "неосторожное преступление")
        return facts()

    result = await extract_case_segments(None, None, texts, [], window_reader=reader)
    assert result.facts.legal_facts.guilt is None
    assert "guilt" in result.extraction.conflicts
    assert len([f for f in result.extraction.facts if f.path == ["guilt"]]) == 2
    assert result.facts.recommended_months is None
    assert any("противореч" in w.lower() for w in result.warnings)


async def test_quote_from_another_window_cannot_validate_fabricated_reading():
    text = "а" * 50000 + "умышленное преступление"
    calls = 0

    async def reader(llm, question, windows, similar):
        nonlocal calls
        calls += 1
        # First window never contained this quote, even though the final document does.
        return facts("intentional", "умышленное преступление") if calls == 1 else facts()

    result = await extract_case_segments(None, None, [text], [], window_reader=reader)
    assert result.facts.legal_facts.guilt is None
    assert result.extraction.rejected
    assert not result.extraction.facts


async def test_one_failed_segment_never_returns_complete_analysis():
    calls = 0

    async def reader(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic unavailable")
        return facts()

    with pytest.raises(RuntimeError, match="synthetic unavailable"):
        await extract_case_segments(None, None, ["а" * 60000], [], window_reader=reader)
    assert calls == 2


async def test_short_documents_keep_one_model_call_and_existing_recommendations():
    seen = []

    async def reader(llm, question, texts, similar):
        seen.append(texts)
        return LlmCaseFacts(fabula="Кратко", recommended_months=12)

    result = await extract_case_segments(None, None, ["первый", "второй"], [], window_reader=reader)
    assert seen == [["первый", "второй"]]
    assert result.facts.recommended_months == 12
    assert result.extraction.complete
    assert len(result.extraction.documents) == 2


async def test_api_saves_complete_coverage_and_quotes_after_old_limit(client, monkeypatch):
    from src.services import analysis_runner

    text = "начало " + "а" * 60000 + " умышленное преступление"
    calls = []

    class SyntheticModel:
        async def complete_json(self, system, user):
            calls.append(user)
            if "умышленное преступление" in user:
                return facts("intentional", "умышленное преступление").model_dump()
            return facts().model_dump()

    monkeypatch.setattr(analysis_runner, "get_llm_client", SyntheticModel)
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь", "use_knowledge_base": "false"},
        files=[("files", ("synthetic.txt", text.encode(), "text/plain"))],
    )
    assert sent.status_code == 202
    message_id = sent.json()["assistant_message"]["id"]
    response = await client.get(f"/api/chats/{chat_id}/messages/{message_id}")
    message = response.json()
    assert message["status"] == "completed", message["error"]
    assert len(calls) == 3
    extraction = message["result"]["extraction"]
    assert extraction["complete"]
    assert extraction["documents"][0]["attachment_id"] is not None
    assert extraction["documents"][0]["filename"] == "synthetic.txt"
    assert extraction["documents"][0]["characters"] == len(text)
    assert extraction["segments"][-1]["end"] == len(text)
    evidence = next(f for f in extraction["facts"] if f["path"] == ["guilt"])
    assert evidence["start"] > 30000
    assert text[evidence["start"] : evidence["end"]] == evidence["quote"]
    assert not any("не полностью" in w for w in message["result"]["warnings"])
    assert (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json() == message


async def test_api_segment_failure_cannot_be_saved_as_success(client, monkeypatch):
    from src.services import analysis_runner
    from src.services.llm_client import LLMError

    class SyntheticModel:
        calls = 0

        async def complete_json(self, system, user):
            self.calls += 1
            if self.calls == 2:
                raise LLMError("synthetic unavailable")
            return facts().model_dump()

    model = SyntheticModel()
    monkeypatch.setattr(analysis_runner, "get_llm_client", lambda: model)
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь", "use_knowledge_base": "false"},
        files=[("files", ("synthetic.txt", ("а" * 60000).encode(), "text/plain"))],
    )
    message_id = sent.json()["assistant_message"]["id"]
    message = (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()
    assert message["status"] == "failed"
    assert message["result"] is None
    assert model.calls == 2


async def test_partial_history_is_not_promoted_to_complete_history():
    calls = 0

    async def reader(*args):
        nonlocal calls
        calls += 1
        return LlmCaseFacts(
            fabula="Фрагмент",
            legal_facts=LegalFacts(history_complete=CitedFact(value=True, quote="ранее не судим"))
            if calls == 1
            else None,
        )

    text = "ранее не судим " + "а" * 40000
    extracted = await extract_case_segments(None, None, [text], [], window_reader=reader)
    assert extracted.facts.legal_facts.history_complete is None


async def test_prior_conflicts_preserve_observations_and_block_complete_history():
    calls = 0
    quote = "сведения о прежнем приговоре"

    async def reader(*args):
        nonlocal calls
        calls += 1
        return LlmCaseFacts(
            fabula="Фрагмент",
            legal_facts=LegalFacts(
                history_complete=CitedFact(value=True, quote=quote),
                prior_convictions=[
                    {
                        "judgment_id": CitedFact(value="synthetic-judgment", quote=quote),
                        "active_at_offence": CitedFact(value=calls == 1, quote=quote),
                    }
                ],
            ),
        )

    extracted = await extract_case_segments(
        None,
        quote,
        ["а" * 40000],
        [],
        window_reader=reader,
    )
    prior = extracted.facts.legal_facts.prior_convictions[0]
    assert "active_at_offence" not in prior
    assert extracted.facts.legal_facts.history_complete is None
    assert any("active_at_offence" in path for path in extracted.extraction.conflicts)
    assert all(f.document_index == -1 for f in extracted.extraction.facts)


async def test_tail_citation_is_usable_by_legal_checks_after_assembly():
    from src.services.case_analyzer import assemble_analysis

    quote = (
        "Преступление умышленное, средней тяжести; назначено лишение свободы. "
        "Подтверждено отсутствие прежних судимостей."
    )
    text = "а" * 60000 + quote

    async def reader(llm, question, windows, similar):
        return LlmCaseFacts(
            fabula="Фрагмент",
            legal_facts=LegalFacts(
                guilt=CitedFact(value="intentional", quote=quote),
                category=CitedFact(value="medium", quote=quote),
                real_imprisonment=CitedFact(value=True, quote=quote),
                history_complete=CitedFact(value=True, quote=quote),
            )
            if quote in windows[0]
            else None,
        )

    # History completeness must be separately supplied for this assembly-only assertion:
    # a single fragment's complete-history claim is intentionally not promoted by the merger.
    extracted = await extract_case_segments(None, None, [text], [], window_reader=reader)
    merged = extracted.facts.model_copy(deep=True)
    merged.legal_facts.history_complete = CitedFact(value=True, quote=quote)
    result = assemble_analysis(
        merged,
        prompt="",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        extraction=extracted.extraction,
    )
    article18 = next(c for c in result.legal_checks if c.norm == "ст. 18 УК РФ")
    assert article18.status == "ok"
    assert quote in article18.evidence
    legacy = assemble_analysis(
        merged,
        prompt="",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
    )
    assert (
        next(c for c in legacy.legal_checks if c.norm == "ст. 18 УК РФ").status
        == "insufficient_data"
    )


async def test_conversation_history_is_not_a_source_of_legal_facts():
    quote = "неподтверждённый ответ прежней модели"

    async def reader(*args):
        return facts("intentional", quote)

    extracted = await extract_case_segments(
        None,
        quote,
        ["а" * 40000],
        [],
        window_reader=reader,
        evidence_question="Текущий вопрос",
    )
    assert extracted.facts.legal_facts.guilt is None
    assert not extracted.extraction.facts
    assert extracted.extraction.rejected
