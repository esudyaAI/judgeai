from copy import deepcopy

import pytest

from src.domain.extraction import input_hash
from src.domain.review_evidence import Evidence, InvalidEvidence, validate_evidence
from src.infrastructure.calculation_inputs import capture_inputs
from src.infrastructure.review_sources import load_review_sources
from src.schemas.analysis import LlmCaseFacts
from tests.test_auth import account, anonymous, login
from tests.test_multidefendant_analysis import TEXT


def captured(text):
    return capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="Вопрос пользователя",
        documents=1,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
    )


def test_frozen_subject_ranges_bind_original_positions_without_rerunning_parser(monkeypatch):
    saved = captured(TEXT)

    def forbidden(*args):
        raise AssertionError("saved subject ranges must not be regenerated")

    monkeypatch.setattr("src.infrastructure.review_sources.defendant_source_spans", forbidden)
    documents, context = load_review_sources(saved)
    assert len(context.subjects) == 2
    start = TEXT.index("на срок 4 года")
    proof = Evidence(0, input_hash(TEXT), start, start + len("на срок 4 года"), "на срок 4 года")
    validate_evidence(documents, context, 1, proof)
    with pytest.raises(InvalidEvidence, match="wrong_subject"):
        validate_evidence(documents, context, 0, proof)
    prompt = "Вопрос пользователя"
    with pytest.raises(InvalidEvidence, match="wrong_subject"):
        validate_evidence(
            documents, context, 0, Evidence(-1, input_hash(prompt), 0, len(prompt), prompt)
        )


def test_changed_text_and_legacy_context_are_rejected_without_backfill():
    saved = captured(TEXT)
    changed = deepcopy(saved)
    changed["kwargs"]["document_texts"][0] += " replaced"
    with pytest.raises(InvalidEvidence, match="documents_changed"):
        load_review_sources(changed)
    saved["contract_version"] = "calculation-inputs/3"
    with pytest.raises(InvalidEvidence, match="unsupported_snapshot"):
        load_review_sources(saved)


def test_unassigned_operative_prefix_is_not_assigned_to_first_person():
    text = TEXT.replace("ПРИГОВОРИЛ:\n", "ПРИГОВОРИЛ:\nНеотнесённая фраза перед назначениями.\n")
    documents, context = load_review_sources(captured(text))
    quote = "Неотнесённая фраза"
    start = text.index(quote)
    for index in range(2):
        with pytest.raises(InvalidEvidence, match="wrong_subject"):
            validate_evidence(
                documents,
                context,
                index,
                Evidence(0, input_hash(text), start, start + len(quote), quote),
            )


async def analysed(client):
    chat = (await client.post("/api/chats", json={"title": "synthetic"})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "Проверь"},
        files=[("files", ("synthetic.txt", TEXT.encode(), "text/plain"))],
    )
    message = sent.json()["assistant_message"]["id"]
    path = f"/api/chats/{chat}/messages/{message}"
    history = (await client.get(path + "/revisions")).json()
    return path, history[0]["id"]


async def test_owned_source_preflight_checks_provenance_without_marking_reviewed(client):
    path, revision = await analysed(client)
    url = path + f"/revisions/{revision}"
    before = (await client.get(url)).json()
    sources = await client.get(url + "/sources")
    assert sources.status_code == 200, sources.text
    assert "no-store" in sources.headers["cache-control"]
    assert "stored_path" not in sources.text
    assert sources.json()["context"]["offset_unit"] == "unicode-codepoint"
    quote = "на срок 4 года"
    start = TEXT.index(quote)
    body = {
        "subject_index": 1,
        "evidence": {
            "document_index": 0,
            "document_hash": input_hash(TEXT),
            "start": start,
            "end": start + len(quote),
            "quote": quote,
        },
    }
    checked = await client.post(url + "/evidence/check", json=body)
    assert checked.status_code == 200 and checked.json()["source_matches"] is True
    assert (await client.get(url)).json() == before
    assert before["review"]["status"] == "not_reviewed"
    assert len((await client.get(path + "/revisions")).json()) == 1
    wrong = {**body, "subject_index": 0}
    assert (await client.post(url + "/evidence/check", json=wrong)).status_code == 422
    assert (
        await client.post(url + "/evidence/check", json={**body, "subject_index": True})
    ).status_code == 422
    token = client.headers.pop("X-CSRF-Token")
    assert (await client.post(url + "/evidence/check", json=body)).status_code == 403
    client.headers["X-CSRF-Token"] = token
    await account("source-stranger")
    async with anonymous() as stranger:
        await login(stranger, "source-stranger")
        assert (await stranger.get(url + "/sources")).status_code == 404
        assert (await stranger.post(url + "/evidence/check", json=body)).status_code == 404


@pytest.mark.parametrize(
    "mutation", ["missing_version", "boolean_coordinate", "duplicate_reference"]
)
def test_malformed_context_does_not_get_guessed_or_silently_normalized(mutation):
    saved = captured(TEXT)
    if mutation == "missing_version":
        saved["review_sources"].pop("scoper_version")
    elif mutation == "boolean_coordinate":
        saved["review_sources"]["subjects"][0]["ranges"][0]["start"] = False
    else:
        saved["kwargs"]["extraction"] = {
            "documents": [
                {"document_index": 0, "document_hash": input_hash(TEXT)},
                {"document_index": 0, "document_hash": input_hash(TEXT)},
            ]
        }
    with pytest.raises(InvalidEvidence):
        load_review_sources(saved)


def test_explicit_common_statement_is_allowed_for_both_and_collective_punishment_is_not_invented():
    text = TEXT.replace(
        "УСТАНОВИЛ:\n", "УСТАНОВИЛ:\nСуд учитывает обоим подсудимым возмещение ущерба.\n\n"
    )
    documents, context = load_review_sources(captured(text))
    quote = "возмещение ущерба"
    start = text.index(quote)
    for subject in range(2):
        validate_evidence(
            documents,
            context,
            subject,
            Evidence(0, input_hash(text), start, start + len(quote), quote),
        )
    collective = (
        "УСТАНОВИЛ:\nsynthetic\nПРИГОВОРИЛ:\n"
        "ФИО1 и ФИО2 признать виновными и назначить по два года лишения свободы."
    )
    documents, context = load_review_sources(captured(collective))
    quote = "по два года лишения свободы"
    start = collective.index(quote)
    for subject in range(2):
        with pytest.raises(InvalidEvidence):
            validate_evidence(
                documents,
                context,
                subject,
                Evidence(0, input_hash(collective), start, start + len(quote), quote),
            )


def test_single_subject_can_cite_the_saved_question_without_other_files():
    saved = capture_inputs(
        LlmCaseFacts(fabula="synthetic"),
        prompt="😀 Вопрос пользователя",
        documents=0,
        pages=0,
        seconds=0,
        similar_items=[],
        extra_warnings=[],
    )
    documents, context = load_review_sources(saved)
    text = documents[0].text
    quote = "Вопрос пользователя"
    start = text.index(quote)
    validate_evidence(
        documents, context, 0, Evidence(-1, input_hash(text), start, start + len(quote), quote)
    )
