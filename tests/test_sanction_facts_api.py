"""T45.3 — sanction questions answered from the law base: API and chat."""

from src.db.session import async_session_factory
from src.services import analysis_runner
from src.services.criminal_sanction_import import import_criminal_sanctions
from tests.test_criminal_sanctions import _seed
from tests.test_practice_facts_chat import _ask

QUESTION = "Какая санкция по ч. 2 ст. 158?"


async def _law_base():
    edition_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, edition_id)


async def test_sanction_question_is_answered_from_the_imported_edition(client):
    await _law_base()
    response = await client.get("/api/legal/sanctions/facts", params={"q": QUESTION})
    assert response.status_code == 200
    body = response.json()
    assert (body["answered"], body["method"], body["parsed"], body["conflict"]) == (
        True,
        "code",
        True,
        False,
    )
    assert body["qualification"] == "ч. 2 ст. 158 УК РФ"
    assert [(s["kind"], s["role"], s["max_value"]) for s in body["sanctions"]] == [
        ("imprisonment", "main", 60),
        ("restriction_of_freedom", "additional", 12),
    ]
    assert body["source"]["source_url"] == "https://pravo.gov.ru/test-fixture"
    assert body["source"]["verification_status"] == "unreviewed"
    assert "лишение свободы до 5 г.; дополнительные — ограничение свободы до 1 г." in body["text"]
    assert "Источник: Synthetic edition, https://pravo.gov.ru/test-fixture" in body["text"]


async def test_unparsed_part_and_unrecognised_question(client):
    await _law_base()
    missing = (
        await client.get(
            "/api/legal/sanctions/facts", params={"q": "Какая санкция по ч. 1 ст. 159?"}
        )
    ).json()
    assert (missing["answered"], missing["parsed"], missing["sanctions"], missing["source"]) == (
        True,
        False,
        [],
        None,
    )
    assert "не разобрана" in missing["text"]
    other = (await client.get("/api/legal/sanctions/facts", params={"q": "Привет"})).json()
    assert other["answered"] is False and "санкци" in other["hint"]


async def test_sanction_question_in_the_chat_needs_no_practice_base(client, monkeypatch):
    def no_model():
        raise AssertionError("the case pipeline must not run for a sanction question")

    monkeypatch.setattr(analysis_runner, "get_llm_client", no_model)
    await _law_base()
    for use_knowledge_base in (True, False):
        _, message = await _ask(client, QUESTION, use_knowledge_base=use_knowledge_base)
        assert message["status"] == "completed", message["error"]
        assert message["result"] is None
        assert (
            "ч. 2 ст. 158 УК РФ: основные наказания — лишение свободы до 5 г." in message["content"]
        )
        assert "https://pravo.gov.ru/test-fixture" in message["content"]
        assert message["fact_answer"] == {"kind": "sanction", "worded_by_model": False}
