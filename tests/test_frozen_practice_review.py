from copy import deepcopy
from dataclasses import replace

from legal_core.precedents import PrecedentEpisode, Qualification, Recidivism
from legal_core.rules.practice_comparison import compare_with_practice

from src.application.practice_report import PracticeReport
from src.infrastructure.calculation_inputs import capture_inputs
from src.infrastructure.frozen_practice import refresh_frozen_practice
from src.schemas.analysis import LlmCaseFacts
from tests.test_episode_practice import card, item, term
from tests.test_sentence_fact_review import TERM, edit

TEXT = "Синтетические материалы. Подсудимый ранее не судимый, действовал умышленно."


def saved_pool(*, multiple=False, shown_only=False):
    from legal_core.entities import ArticleReference, CountSentence, ImposedSentence

    first = PrecedentEpisode(Qualification("158", 2), term(24))
    second = PrecedentEpisode(Qualification("161", 1), term(48))
    episodes = [first, second] if multiple else [first]
    candidates = [
        item(i, card([replace(first, punishment=term(i))], Recidivism.NONE)) for i in range(1, 64)
    ]
    if multiple:
        candidates.append(item(100, card([second], Recidivism.NONE)))
    query = card(episodes, Recidivism.NONE)
    query = replace(query, fabula="Сохранённая синтетическая фабула")
    report = PracticeReport(
        query,
        candidates[:10],
        len(candidates),
        0,
        True,
        compare_with_practice([c.stored.card for c in candidates], 24),
        candidate_pool=[] if shown_only else candidates,
    )
    sentence = ImposedSentence(
        counts=tuple(
            CountSentence(
                str(e.qualification),
                ArticleReference(e.qualification.article, e.qualification.part),
                e.punishment,
                quote=TEXT,
            )
            for e in episodes
        )
    )
    payload = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[TEXT],
        sentence=sentence,
        practice=report,
    )
    legal = payload["kwargs"]["prepared_legal_inputs"]["0"]
    legal.update(stated_recidivism="none", stated_quote="ранее не судимый")
    return payload


async def test_refilter_recomputes_all_retained_terms_and_percentile_without_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("no mutable corpus, model or embedding call allowed")

    monkeypatch.setattr("src.infrastructure.fastembed_embedder.embed_query", forbidden)
    monkeypatch.setattr("src.services.case_analyzer.extract_facts", forbidden)
    payload = saved_pool()
    before = deepcopy(payload)
    edited, preliminary, _ = edit(payload, "sentence/count/0/main", {**TERM, "amount": 99})
    updated, result = await refresh_frozen_practice(edited, preliminary)
    comparison = result["practice_episodes"][0]
    assert comparison["with_term"] == 63
    assert comparison["median_months"] == 32
    assert comparison["draft_months"] == 99 and comparison["draft_percentile"] == 100
    assert comparison["vector_used"] is False
    assert len(result["precedents"]) == 10
    assert len(updated["review_practice_baseline"]["0"]["candidate_pool"]) == 63
    assert updated["review_invalidations"] == []
    assert payload == before
    assert any("только из сохранённой выборки" in w for w in result["warnings"])


async def test_later_correction_recovers_candidates_from_original_bank():
    payload = saved_pool(multiple=True)
    edited, preliminary, _ = edit(payload, "sentence/count/0/qualification", "ч. 1 ст. 162 УК РФ")
    updated, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice_episodes"][0]["with_term"] == 0
    assert result["practice_episodes"][1]["with_term"] == 1
    assert len(updated["kwargs"]["practice"]["candidate_pool"]) == 1
    assert len(updated["review_practice_baseline"]["0"]["candidate_pool"]) == 64
    edited, preliminary, _ = edit(updated, "sentence/count/0/qualification", "ч. 2 ст. 158 УК РФ")
    restored, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice_episodes"][0]["with_term"] == 63
    assert len(restored["review_practice_baseline"]["0"]["candidate_pool"]) == 64


async def test_changed_recidivism_uses_current_check_and_recomputes_statistics():
    edited, preliminary, _ = edit(saved_pool(), "legal/stated_recidivism", "dangerous")
    updated, result = await refresh_frozen_practice(edited, preliminary)
    assert updated["kwargs"]["practice"]["query"]["recidivism"] == "dangerous"
    assert result["practice_episodes"][0]["with_term"] == 0
    assert result["practice_episodes"][0]["enough_data"] is False


async def test_unknown_inputs_do_not_become_false_or_keep_old_distribution():
    edited, preliminary, _ = edit(saved_pool(), "sentence/conditional", operation="unknown")
    updated, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice"] is None and result["practice_episodes"] == []
    assert updated["kwargs"]["practice"] is None
    assert len(updated["review_practice_baseline"]["0"]["candidate_pool"]) == 63
    assert updated["review_practice_refresh"]["subjects"]["0"]["status"] == "unavailable"
    assert any("Условность" in w for w in result["warnings"])
    edited, preliminary, _ = edit(updated, "sentence/conditional", False)
    _, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice_episodes"][0]["with_term"] == 63


async def test_shown_only_legacy_bank_has_an_explicit_smaller_denominator():
    edited, preliminary, _ = edit(saved_pool(shown_only=True), "sentence/count/0/main", TERM)
    updated, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice_episodes"][0]["with_term"] == 10
    assert updated["review_practice_refresh"]["subjects"]["0"]["basis"] == "shown_only"
    assert any("только ранее показанный" in w for w in result["warnings"])


async def test_fine_credit_unknown_blocks_refilter_without_claiming_release():
    credit = {
        "scope": "count",
        "count_index": 0,
        "original_amount": 10000,
        "reduced_amount": 5000,
        "released": False,
        "status": "stated",
    }
    payload, _, _ = edit(saved_pool(), "sentence/fine_credit/new", credit)
    payload, result, _ = edit(payload, "sentence/fine_credit/0", operation="unknown")
    updated, result = await refresh_frozen_practice(payload, result)
    assert result["imposed_sentence"]["fine_credits"][0]["released"] is None
    assert result["imposed_sentence"]["fine_credits"][0]["unknown"] is True
    assert result["practice"] is None
    assert updated["review_practice_refresh"]["subjects"]["0"]["status"] == "unavailable"


async def test_fractional_day_terms_survive_typed_snapshot_and_refilter():

    payload = saved_pool()
    # The frozen corpus can contain exact day terms, not just whole-month caches.
    for candidate in payload["kwargs"]["practice"]["candidate_pool"]:
        candidate["stored"]["card"]["episodes"][0]["punishment"] = {
            "kind": "imprisonment",
            "amount": 15,
            "unit": "days",
        }
    payload["kwargs"]["practice"]["comparison"].update(
        min_months=0.5, max_months=0.5, draft_months=0.5
    )
    edited, preliminary, _ = edit(
        payload, "sentence/count/0/main", {"kind": "imprisonment", "amount": 15, "unit": "days"}
    )
    updated, result = await refresh_frozen_practice(edited, preliminary)
    assert result["practice_episodes"][0]["min_months"] == 0.5
    assert result["practice_episodes"][0]["draft_months"] == 0.5
    assert result["practice_episodes"][0]["draft_percentile"] == 50
    assert updated["kwargs"]["practice"]["comparison"]["min_months"] == 0.5


async def api_saved_pool(client):
    from src.db.models import Chat, Message
    from src.db.session import async_session_factory
    from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore
    from src.infrastructure.calculation_inputs import replay_inputs

    chat = (await client.post("/api/chats", json={"title": "Synthetic frozen practice"})).json()[
        "id"
    ]
    response = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "Проверь", "use_knowledge_base": "false"},
        files=[("files", ("synthetic.txt", TEXT.encode(), "text/plain"))],
    )
    message_id = response.json()["assistant_message"]["id"]
    payload = saved_pool()
    async with async_session_factory() as db:
        owner = (await db.get(Chat, chat)).owner_id
        row = await SqlAnalysisRevisionStore(db).append(
            owner, chat, message_id, replay_inputs(payload).model_dump(mode="json"), payload
        )
        (await db.get(Message, message_id)).analysis = row.result
        await db.commit()
    return f"/api/chats/{chat}/messages/{message_id}", str(row.id)


def api_command(base):
    from uuid import uuid4

    from src.domain.extraction import input_hash

    return {
        "base_revision_id": base,
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/0/sentence/count/0/main",
                "operation": "correct",
                "value": {**TERM, "amount": 99},
                "reason": "Синтетический пересчёт",
                "evidence": {
                    "document_index": 0,
                    "document_hash": input_hash(TEXT),
                    "start": 0,
                    "end": len(TEXT),
                    "quote": TEXT,
                },
            }
        ],
    }


async def test_actual_review_and_practice_endpoint_use_frozen_report_not_live_store(
    client, monkeypatch
):
    from src.api.precedents import get_embedder
    from src.main import app
    from tests.test_auth import account, anonymous, login

    path, base = await api_saved_pool(client)
    old_report = (await client.post(path + "/reports")).json()
    artifact_url = f"/api/reports/{old_report['id']}/docx"
    old_bytes = (await client.get(artifact_url)).content

    def forbidden(*args, **kwargs):
        raise AssertionError("No live precedent store or embedding allowed")

    monkeypatch.setattr("src.infrastructure.precedent_store.SqlPrecedentStore.__init__", forbidden)
    app.dependency_overrides[get_embedder] = lambda: object()
    try:
        body = api_command(base)
        saved = await client.post(path + "/review", json=body)
        assert saved.status_code == 200, saved.text
        result = saved.json()
        assert result["practice_episodes"][0]["with_term"] == 63
        assert result["practice_episodes"][0]["draft_months"] == 99
        assert result["human_review"]["practice_invalidated"] is False
        assert (await client.post(path + "/review", json=body)).json() == result
        practice_path = path.rsplit("/messages/", 1)[0] + "/precedents"
        practice = await client.get(practice_path)
        assert practice.status_code == 200, practice.text
        assert len(practice.json()["items"]) == 10
        assert len((await client.get(practice_path + "?limit=50")).json()["items"]) == 50
        assert practice.json()["vector_used"] is False
        assert "сохранённой выборки" in practice.json()["note"]
        assert "no-store" in practice.headers["cache-control"]
        assert (await client.get(artifact_url)).content == old_bytes
        detail = (await client.get(path + "/revisions/" + result["revision"]["id"])).json()
        assert (
            len(detail["calculation_inputs"]["review_practice_baseline"]["0"]["candidate_pool"])
            == 63
        )
        assert (
            detail["result"]["provenance"]["practice_review"]["version"]
            == "frozen-practice-review/1"
        )
        assert (await client.post(path + "/reports")).status_code == 201
        await account("frozen-pool-stranger")
        async with anonymous() as stranger:
            await login(stranger, "frozen-pool-stranger")
            assert (await stranger.get(practice_path)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_embedder, None)


async def test_refilter_failure_rolls_back_and_does_not_consume_request_uuid(
    client, monkeypatch, caplog
):
    from src.infrastructure.fact_review import FrozenReviewCalculator

    path, base = await api_saved_pool(client)
    before = (await client.get(path)).json()["result"]
    refresh = FrozenReviewCalculator.refresh_practice

    async def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-SYNTHETIC-REFILTER")

    monkeypatch.setattr(FrozenReviewCalculator, "refresh_practice", fail)
    body = api_command(base)
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 503, response.text
    assert "PRIVATE-SYNTHETIC-REFILTER" not in response.text + caplog.text
    assert (await client.get(path)).json()["result"] == before
    assert len((await client.get(path + "/revisions")).json()) == 2
    monkeypatch.setattr(FrozenReviewCalculator, "refresh_practice", refresh)
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 200 and response.json()["revision"]["version"] == 3


async def test_explicit_unknown_circumstance_is_not_known_absence_in_matching():
    value = {
        "name": "Синтетическое обстоятельство",
        "norm": "п. «и» ч. 1 ст. 61 УК РФ",
        "established": True,
    }
    payload, _, _ = edit(saved_pool(), "circumstance/mitigating/new", value)
    payload, result, _ = edit(payload, "circumstance/mitigating/0", operation="unknown")
    updated, result = await refresh_frozen_practice(payload, result)
    assert result["practice"] is None
    assert "обстоятельства" in updated["review_practice_refresh"]["subjects"]["0"]["reason"]
    payload, result, _ = edit(updated, "circumstance/mitigating/0", value)
    _, result = await refresh_frozen_practice(payload, result)
    assert result["practice_episodes"][0]["with_term"] == 63


async def test_each_person_uses_only_their_own_bank_and_never_the_global_pool():
    from src.domain.fact_review import FactDecision, apply_decisions
    from src.domain.review_evidence import Evidence
    from src.infrastructure.fact_review import FrozenReviewCalculator
    from tests.test_fact_review import proof
    from tests.test_multidefendant_analysis import TEXT as MULTI

    first = card([PrecedentEpisode(Qualification("158", 1), term(12))], Recidivism.NONE)
    second = card([PrecedentEpisode(Qualification("161", 2), term(48))], Recidivism.DANGEROUS)

    def report(number, value):
        candidate = item(number, value)
        return PracticeReport(
            value,
            [candidate],
            1,
            0,
            False,
            compare_with_practice([value], value.imprisonment_months),
            candidate_pool=[candidate],
        )

    own = {0: report(1, first), 1: report(2, second)}
    payload = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="",
        documents=1,
        pages=1,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[MULTI],
        practice=report(99, second),
        defendant_practice=own,
    )
    calculator = FrozenReviewCalculator()
    prepared = calculator.prepare(payload)
    decision = FactDecision(
        "subject/1/sentence/count/0/main",
        "correct",
        "Синтетическая проверка",
        {**TERM, "amount": 60},
        Evidence(**proof()),
    )
    legal, sentencing, _, changed = apply_decisions(
        prepared.legal, prepared.sentencing, prepared.documents, prepared.context, (decision,)
    )
    edited, result = calculator.calculate(payload, legal, sentencing, changed)
    updated, result = await refresh_frozen_practice(edited, result)
    assert [p["practice_episodes"][0]["median_months"] for p in result["defendants"]] == [12, 48]
    assert result["defendants"][1]["practice_episodes"][0]["draft_months"] == 60
    assert [
        updated["review_practice_baseline"][str(i)]["candidate_pool"][0]["stored"]["id"]
        for i in (0, 1)
    ] == [1, 2]
    # Even a global pool that contains matching cards must not fill a missing personal bank.
    missing = deepcopy(payload)
    missing["kwargs"]["defendant_practice"].pop("1")
    prepared = calculator.prepare(missing)
    legal, sentencing, _, changed = apply_decisions(
        prepared.legal, prepared.sentencing, prepared.documents, prepared.context, (decision,)
    )
    edited, result = calculator.calculate(missing, legal, sentencing, changed)
    updated, result = await refresh_frozen_practice(edited, result)
    assert result["defendants"][1]["practice_episodes"] == []
    assert updated["review_practice_refresh"]["subjects"]["1"]["status"] == "unavailable"
