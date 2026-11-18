"""T45.5 — a factual question in a chat that already holds case documents.

The question is answered by code from the shared base, as in a chat without documents, and the
answer says plainly that the case documents of the chat were not part of it.
"""

from src.domain.fact_answer_scope import case_documents_note
from src.services import analysis_runner
from tests.test_practice_facts_chat import QUESTION, _base

CASE = [("files", ("Проект.txt", "Подсудимый похитил ноутбук".encode(), "text/plain"))]


async def _case_chat(client):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    r = await client.post(f"/api/chats/{chat_id}/messages", data={"content": "Проверь"}, files=CASE)
    assert r.status_code == 202
    return chat_id


async def _say(client, chat_id, content, files=None):
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": content, "use_knowledge_base": "true"},
        files=files,
    )
    assert r.status_code == 202
    message_id = r.json()["assistant_message"]["id"]
    return (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()


def test_note_only_when_the_chat_holds_case_documents():
    assert case_documents_note("practice", has_case_documents=False) is None
    assert case_documents_note("sanction", has_case_documents=False) is None
    practice = case_documents_note("practice", has_case_documents=True)
    assert "документы дела из этого чата" in practice
    assert "не сравнивался" in practice
    sanction = case_documents_note("sanction", has_case_documents=True)
    assert "дата преступления" in sanction


async def test_practice_question_after_the_case_is_answered_by_code_with_a_note(
    client, monkeypatch
):
    await _base()
    chat_id = await _case_chat(client)

    def no_model():
        raise AssertionError("the case pipeline must not run for a practice question")

    monkeypatch.setattr(analysis_runner, "get_llm_client", no_model)
    message = await _say(client, chat_id, QUESTION)

    assert message["status"] == "completed", message["error"]
    assert message["result"] is None
    assert message["fact_answer"] == {"kind": "practice", "worded_by_model": False}
    text = message["content"]
    assert "среднее 2 г." in text
    assert text.rstrip().endswith(case_documents_note("practice", has_case_documents=True))


async def test_question_with_its_own_document_stays_a_case_analysis(client):
    await _base()
    chat_id = await _case_chat(client)
    message = await _say(client, chat_id, QUESTION, files=CASE)
    assert message["status"] == "completed"
    assert message["result"] is not None
    assert message["fact_answer"] is None


async def test_other_follow_up_questions_still_analyse_the_case(client):
    await _base()
    chat_id = await _case_chat(client)
    message = await _say(client, chat_id, "Проверь наказание ещё раз")
    assert message["status"] == "completed"
    assert message["result"] is not None
    assert message["fact_answer"] is None


async def test_question_without_case_documents_has_no_note(client):
    await _base()
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    message = await _say(client, chat_id, QUESTION)
    assert "документы дела" not in message["content"]
