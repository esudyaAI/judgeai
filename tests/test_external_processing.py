"""Capture the real transport payloads, using MockTransport and synthetic identities only."""

import json
import logging

import httpx
import pytest

from src.domain.privacy import ExternalProcessingPolicy
from src.services import embeddings, llm_client
from src.services.embeddings import JinaEmbeddings
from src.services.external_processing import GuardedEmbeddings, GuardedLLMClient
from src.services.llm_client import LLMError, OpenAICompatibleClient

BASE = "https://synthetic.invalid/v1"
PERSON = "Иванов Иван Иванович"
SOURCE = f"Подсудимый {PERSON} признал вину. Телефон +7 (999) 123-45-67."
APPROVED = ExternalProcessingPolicy("synthetic-decision", (BASE,))


async def test_factory_masks_actual_http_body_and_restores_citation(monkeypatch, caplog):
    captured = []

    def handle(request):
        captured.append(request)
        body = json.loads(request.content)
        quote = body["messages"][1]["content"].split("\n\n")[0]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"quote": quote})}}]}
        )

    original = llm_client.OpenAICompatibleClient
    monkeypatch.setattr(
        llm_client,
        "OpenAICompatibleClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_client.settings, "LLM_FALLBACK_PROVIDER", "none")
    monkeypatch.setattr(llm_client.settings, "LLM_API_BASE", BASE)
    monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        llm_client.settings, "EXTERNAL_PROCESSING_APPROVAL_ID", "synthetic-decision"
    )
    monkeypatch.setattr(llm_client.settings, "EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS", BASE)
    with caplog.at_level(logging.DEBUG):
        result = await llm_client.get_llm_client().complete_json("Extract JSON.", SOURCE)
    assert result["quote"] == SOURCE
    wire = captured[0].content.decode()
    assert PERSON not in wire and "+7 (999) 123-45-67" not in wire
    assert "[JAI_" in wire
    assert "synthetic-key" not in wire
    assert captured[0].headers["Authorization"] == "Bearer synthetic-key"
    assert PERSON not in caplog.text and "synthetic-key" not in caplog.text


@pytest.mark.parametrize(
    "policy,endpoint",
    [
        (ExternalProcessingPolicy(None, (BASE,)), BASE),
        (APPROVED, "https://other.invalid/v1"),
        (ExternalProcessingPolicy("synthetic", (BASE + "?secret=key",)), BASE + "?secret=key"),
    ],
)
async def test_no_network_without_a_valid_decision_and_exact_safe_destination(policy, endpoint):
    class Never:
        calls = 0

        async def complete_json(self, *args):
            self.calls += 1
            return {}

    backend = Never()
    with pytest.raises(LLMError, match="не согласована"):
        await GuardedLLMClient(backend, endpoint, policy).complete_json("system", SOURCE)
    assert backend.calls == 0


async def test_unknown_returned_pseudonym_is_rejected_without_echoing_output():
    class Forged:
        async def complete_json(self, *args):
            return {"quote": "[JAI_" + "f" * 32 + "_999]"}

    with pytest.raises(LLMError) as error:
        await GuardedLLMClient(Forged(), BASE, APPROVED).complete_json("system", SOURCE)
    assert "JAI_" not in str(error.value)
    assert PERSON not in str(error.value)


async def test_cloud_embeddings_are_redacted_and_stable_across_calls():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    backend = JinaEmbeddings(
        "synthetic-key", "synthetic-model", 2, base=BASE, transport=httpx.MockTransport(handle)
    )
    client = GuardedEmbeddings(backend, BASE, APPROVED)
    assert await client.embed([SOURCE], "retrieval.query") == [[0.5, 0.5]]
    await client.embed([SOURCE], "retrieval.query")
    bodies = [json.loads(request.content) for request in requests]
    assert bodies[0]["input"] == bodies[1]["input"]
    assert PERSON not in requests[0].content.decode()
    assert "JAI_" not in requests[0].content.decode()
    assert "скрыто" in bodies[0]["input"][0]


async def test_provider_error_bodies_and_transport_messages_are_not_logged(monkeypatch, caplog):
    sentinel = "PRIVATE-CONTENT synthetic-key"
    monkeypatch.setattr(llm_client, "LLM_ATTEMPTS", 1)

    def denied(request):
        return httpx.Response(400, text=sentinel)

    client = OpenAICompatibleClient(BASE, "synthetic-key", transport=httpx.MockTransport(denied))
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError):
        await client.complete_json("system", SOURCE)
    assert sentinel not in caplog.text

    def broken(request):
        raise httpx.ConnectError(sentinel, request=request)

    client = OpenAICompatibleClient(BASE, "synthetic-key", transport=httpx.MockTransport(broken))
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError):
        await client.complete_json("system", SOURCE)
    assert sentinel not in caplog.text


async def test_untrusted_usage_fields_are_not_echoed_to_logs(caplog):
    sentinel = "PRIVATE-CONTENT synthetic-key"

    def handle(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": sentinel, "completion_tokens": sentinel},
            },
        )

    client = OpenAICompatibleClient(BASE, "synthetic-key", transport=httpx.MockTransport(handle))
    with caplog.at_level(logging.DEBUG):
        assert await client.complete_json("system", SOURCE) == {}
    assert sentinel not in caplog.text


def test_jina_cache_identity_includes_transform_version(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "jina")
    assert embeddings.embedding_cache_model("model") == "model::privacy-redaction/1"
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "fastembed")
    assert embeddings.embedding_cache_model("model") == "model"


async def test_full_materials_hide_aliases_outside_the_current_window():
    class Echo:
        seen = ""

        async def complete_json(self, system, user):
            self.seen = user
            return {"quote": user}

    backend = Echo()
    client = GuardedLLMClient(backend, BASE, APPROVED).with_materials(
        ("Подсудимый Иванов Иван Иванович признал вину.",)
    )
    result = await client.complete_json("system", "Поздний фрагмент: Иванову передали сообщение.")
    assert "Иванов" not in backend.seen
    assert result["quote"] == "Поздний фрагмент: Иванову передали сообщение."


async def test_source_window_is_expanded_before_a_partial_phone_can_leave():
    class Echo:
        seen = ""

        async def complete_json(self, system, user):
            self.seen = user
            return {"quote": user}

    source = "Назначить наказание. Телефон +7 (999) 123-45-67. Следующее предложение."
    fragment = source[: source.index("45-67")]
    backend = Echo()
    client = GuardedLLMClient(backend, BASE, APPROVED).with_materials((source,))
    result = await client.complete_json("system", fragment)
    assert "+7 (999)" not in backend.seen
    assert "+7 (999) 123-45-67" in result["quote"]


async def test_embeddings_mask_before_the_text_length_limit():
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5]}]})

    raw = "a" * 7985 + " Подсудимый Иванов Иван Иванович признал вину."
    backend = JinaEmbeddings(
        "synthetic-key", "model", 1, base=BASE, transport=httpx.MockTransport(handle)
    )
    await GuardedEmbeddings(backend, BASE, APPROVED).embed([raw], "retrieval.query")
    assert "Иван" not in requests[0]["input"][0]


async def test_api_protects_identifiers_across_long_document_windows(client, monkeypatch, caplog):
    original = llm_client.OpenAICompatibleClient
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"fabula":"Синтетический результат"}'}}]},
        )

    monkeypatch.setattr(
        llm_client,
        "OpenAICompatibleClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handle)),
    )
    for name, value in {
        "LLM_PROVIDER": "openai",
        "LLM_FALLBACK_PROVIDER": "none",
        "LLM_API_BASE": BASE,
        "LLM_API_KEY": "synthetic-key",
        "EXTERNAL_PROCESSING_APPROVAL_ID": "synthetic-only",
        "EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS": BASE,
    }.items():
        monkeypatch.setattr(llm_client.settings, name, value)
    intro = f"Подсудимый {PERSON}.\n"
    phone = "+7 (999) 123-45-67"
    text = intro + "а" * (27990 - len(intro)) + phone + "а" * 32000 + "\nИВАНОВУ разъяснены права."
    chat = (await client.post("/api/chats", json={"title": None})).json()["id"]
    with caplog.at_level(logging.DEBUG):
        sent = await client.post(
            f"/api/chats/{chat}/messages",
            data={"content": "Проверь", "use_knowledge_base": "false"},
            files=[("files", ("synthetic.txt", text.encode(), "text/plain"))],
        )
        message_id = sent.json()["assistant_message"]["id"]
        reply = (await client.get(f"/api/chats/{chat}/messages/{message_id}")).json()
    assert reply["status"] == "completed", reply["error"]
    assert len(captured) == 3
    wire = json.dumps(captured, ensure_ascii=False)
    assert "Иван" not in wire and "ИВАНОВ" not in wire and phone not in wire
    assert PERSON not in caplog.text and "synthetic-key" not in caplog.text
    spans = reply["result"]["extraction"]["segments"]
    for segment in spans:
        assert not 27990 < segment["start"] < 27990 + len(phone)
        assert not 27990 < segment["end"] < 27990 + len(phone)


async def test_api_does_not_use_primary_or_fallback_without_approval(client, monkeypatch, caplog):
    class Never:
        calls = 0

        async def complete_json(self, *args):
            self.calls += 1
            raise AssertionError("must never send")

    backend = Never()
    monkeypatch.setattr(llm_client, "OpenAICompatibleClient", lambda **kw: backend)
    monkeypatch.setattr(llm_client, "DeepSeekWebClient", lambda **kw: backend)
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "fallback")
    monkeypatch.setattr(llm_client.settings, "EXTERNAL_PROCESSING_APPROVAL_ID", None)
    monkeypatch.setattr(llm_client.settings, "EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS", "")
    chat = (await client.post("/api/chats", json={"title": None})).json()["id"]
    with caplog.at_level(logging.DEBUG):
        sent = await client.post(
            f"/api/chats/{chat}/messages",
            data={"content": SOURCE, "use_knowledge_base": "false"},
        )
        reply = (
            await client.get(f"/api/chats/{chat}/messages/{sent.json()['assistant_message']['id']}")
        ).json()
    assert reply["status"] == "failed" and reply["result"] is None
    assert "не согласована" in reply["error"]
    assert backend.calls == 0
    assert PERSON not in caplog.text


async def test_fallback_uses_its_own_guard_and_restores_its_citation(monkeypatch, caplog):
    fallback_base = "https://fallback.invalid/v1"
    captured = []
    primary_type, fallback_type = llm_client.OpenAICompatibleClient, llm_client.DeepSeekWebClient

    def primary(request):
        captured.append(request)
        return httpx.Response(503, text="PRIVATE synthetic-key")

    def fallback(request):
        captured.append(request)
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        text = body["messages"][0]["content"].split("\n\n---\n\n", 1)[1]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"quote": text})}}]}
        )

    monkeypatch.setattr(
        llm_client,
        "OpenAICompatibleClient",
        lambda **kw: primary_type(**kw, transport=httpx.MockTransport(primary)),
    )
    monkeypatch.setattr(
        llm_client,
        "DeepSeekWebClient",
        lambda **kw: fallback_type(**kw, transport=httpx.MockTransport(fallback)),
    )
    monkeypatch.setattr(llm_client, "LLM_ATTEMPTS", 1)
    for name, value in {
        "LLM_PROVIDER": "fallback",
        "LLM_API_BASE": BASE,
        "LLM_API_KEY": "synthetic-key",
        "LLM_FALLBACK_API_BASE": fallback_base,
        "LLM_FALLBACK_API_KEY": "synthetic-fallback-key",
        "EXTERNAL_PROCESSING_APPROVAL_ID": "synthetic-only",
        "EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS": BASE + "," + fallback_base,
    }.items():
        monkeypatch.setattr(llm_client.settings, name, value)
    with caplog.at_level(logging.DEBUG):
        result = await llm_client.get_llm_client().complete_json("system", SOURCE)
    posts = [r for r in captured if r.method == "POST"]
    assert len(posts) == 2
    assert result["quote"] == SOURCE
    assert all(PERSON not in r.content.decode() for r in posts)
    assert PERSON not in caplog.text and "synthetic-key" not in caplog.text
    assert "synthetic-fallback-key" not in caplog.text


async def test_validation_retry_does_not_forward_private_values_from_the_bad_output(caplog):
    from src.services.case_analyzer import extract_facts

    private = "SYNTHETIC-PRIVATE-INVALID-VALUE"

    class InvalidThenValid:
        prompts = []

        async def complete_json(self, system, user):
            self.prompts.append(user)
            if len(self.prompts) == 1:
                return {
                    "fabula": "synthetic",
                    "legal_facts": {"guilt": {"value": [private], "quote": "synthetic quote"}},
                }
            return {"fabula": "synthetic"}

    backend = InvalidThenValid()
    with caplog.at_level(logging.DEBUG):
        await extract_facts(backend, "Check", ["synthetic text"], [])
    assert len(backend.prompts) == 2
    assert private not in backend.prompts[1] and private not in caplog.text


async def test_embedding_uses_names_known_only_from_full_materials():
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5]}]})

    backend = JinaEmbeddings(
        "synthetic-key", "model", 1, base=BASE, transport=httpx.MockTransport(handle)
    )
    client = GuardedEmbeddings(backend, BASE, APPROVED).with_materials(
        ("Подсудимый Иванов Иван Иванович, потерпевшая Петрова Анна Сергеевна.",)
    )
    await client.embed(["Иванову передано имущество Петровой."], "retrieval.query")
    wire = json.dumps(requests, ensure_ascii=False)
    assert "Иванов" not in wire and "Петров" not in wire


def test_fabula_prefix_does_not_cut_a_known_identifier():
    from src.infrastructure.fabula import extract_fabula

    intro = "Подсудимый Иванов Иван Иванович."
    description = "а" * 2997 + " Иванову передано имущество."
    fabula = extract_fabula(description, materials=(intro, description))
    assert not fabula.endswith("Ив")
    assert fabula == "а" * 2997


def test_context_adapter_preserves_timeout_and_vector_cache_identity(monkeypatch):
    from src.infrastructure.bounded_embedder import BoundedQueryEmbedder
    from src.infrastructure.fastembed_embedder import FastembedEmbedder, with_embedding_materials

    monkeypatch.setattr(embeddings.settings, "EMBEDDING_PROVIDER", "jina")
    original = BoundedQueryEmbedder(FastembedEmbedder("synthetic-model"), timeout=7)
    bound = with_embedding_materials(original, ("Подсудимый Иванов Иван Иванович.",))
    assert bound is not original and bound.timeout == 7
    assert bound.model_name == original.model_name == "synthetic-model::privacy-redaction/1"
    assert not original.embedder.materials


async def test_precedent_api_sends_no_bare_surname_to_cloud_embedding(client, monkeypatch):
    # Override only the global no-network stub; HTTP remains intercepted by MockTransport.
    monkeypatch.setattr("src.infrastructure.fastembed_embedder.embed_query", embeddings.embed_query)
    requests = []
    _jina_context_transport(monkeypatch, requests)
    text = (
        "Иванов Иван Иванович, ранее не судим.\nУСТАНОВИЛ:\n"
        "Иванов тайно похитил телефон стоимостью 20000 рублей.\nПРИГОВОРИЛ:\n"
        "Признать Иванова виновным по ч. 1 ст. 158 УК РФ и назначить "
        "наказание в виде лишения свободы на срок 1 год."
    )
    chat = (await client.post("/api/chats", json={"title": None})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "Проверь", "use_knowledge_base": "false"},
        files=[("files", ("synthetic.txt", text.encode(), "text/plain"))],
    )
    assert sent.status_code == 202
    response = await client.get(f"/api/chats/{chat}/precedents?defendant=1")
    assert response.status_code == 200, response.text
    assert requests, response.json()
    assert response.json()["vector_used"] is True
    assert "Иван" not in json.dumps(requests, ensure_ascii=False)
    assert "скрыто" in requests[0]["input"][0]


def _jina_context_transport(monkeypatch, requests):
    original_type = embeddings.JinaEmbeddings

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    monkeypatch.setattr(
        embeddings,
        "JinaEmbeddings",
        lambda *args, **kw: original_type(*args, **kw, transport=httpx.MockTransport(handle)),
    )
    for name, value in {
        "EMBEDDING_PROVIDER": "jina",
        "EMBEDDING_ENABLED": True,
        "EMBEDDING_DIM": 2,
        "EMBEDDING_MODEL": "synthetic-model",
        "JINA_API_KEY": "synthetic-key",
        "JINA_API_BASE": BASE,
        "EXTERNAL_PROCESSING_APPROVAL_ID": "synthetic-only",
        "EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS": BASE,
    }.items():
        monkeypatch.setattr(embeddings.settings, name, value)


async def test_legacy_search_uses_full_materials_for_cloud_query(monkeypatch):
    from src.db.session import async_session_factory
    from src.services import similarity_search

    requests = []
    _jina_context_transport(monkeypatch, requests)
    monkeypatch.setattr(similarity_search, "embed_query", embeddings.embed_query)
    async with async_session_factory() as db:
        await similarity_search.find_similar_verdicts(
            db,
            "Иванов похитил имущество.",
            ["Подсудимый Иванов Иван Иванович."],
        )
    assert len(requests) == 1
    assert "Иван" not in json.dumps(requests, ensure_ascii=False)


async def test_shared_chunk_upload_and_reembed_use_original_source_context(monkeypatch):
    from src.db.session import async_session_factory
    from src.services import knowledge_service

    requests = []
    _jina_context_transport(monkeypatch, requests)
    monkeypatch.setattr(knowledge_service, "embed_passages", embeddings.embed_passages)
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_MAX_CHUNKS", 1)
    raw = "Иванов похитил имущество. " + "а" * 3000 + "\nПодсудимый Иванов Иван Иванович."
    async with async_session_factory() as db:
        row, _ = await knowledge_service.create_knowledge_verdict_from_text(
            db, "synthetic.txt", raw
        )
        assert row.raw_text == raw
        await db.commit()
    assert len(requests) == 1
    assert "Иван" not in json.dumps(requests, ensure_ascii=False)
    # A new model forces a later reembed; the first batch contains no full name of its own.
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_MODEL", "synthetic-new-model")
    async with async_session_factory() as db:
        assert await knowledge_service.reembed_knowledge_chunks(db, batch=1) == 2
    assert len(requests) == 3
    assert "Иван" not in json.dumps(requests, ensure_ascii=False)


async def test_provenance_records_only_successful_call_metadata_and_prompt_hash():
    from hashlib import sha256

    from src.services.llm_client import llm_provenance

    backend = OpenAICompatibleClient(
        api_base=BASE,
        api_key="synthetic-secret",
        model="synthetic-revision",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": '{"value": null}'}}]}
            )
        ),
    )
    client = GuardedLLMClient(backend, BASE, APPROVED).with_materials((SOURCE,))
    assert llm_provenance(client)["calls"] == []
    await client.complete_json("Extract JSON.", SOURCE)
    result = llm_provenance(client)
    assert result["resolved_model_revision"] is None
    assert result["calls"][0]["requested_model"] == "synthetic-revision"
    assert result["calls"][0]["system_prompt_sha256"] == sha256(b"Extract JSON.").hexdigest()
    assert PERSON not in str(result) and "synthetic-secret" not in str(result)
    assert BASE not in str(result)
    assert GuardedLLMClient(backend, BASE, APPROVED).receipts == []
