"""T45.2 — a practice question in the chat is answered from numbers counted by code."""

from src.infrastructure.practice_phraser import LlmAnswerPhraser
from src.services import analysis_runner
from src.services.llm_client import LLMError
from tests.fixtures.synthetic_verdicts import PRACTICE_ROBBERY
from tests.test_practice_facts_api import TERMS, _add, _theft

QUESTION = "Какой средний срок по ч. 2 ст. 158?"


class Phraser:
    def __init__(self, wording):
        self.wording, self.calls = wording, []

    async def phrase(self, qualification, facts_text):
        self.calls.append((qualification, facts_text))
        return self.wording


async def _ask(client, content, files=None, use_knowledge_base=True):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": content, "use_knowledge_base": str(use_knowledge_base).lower()},
        files=files,
    )
    assert r.status_code == 202
    message_id = r.json()["assistant_message"]["id"]
    message = (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()
    return chat_id, message


async def _base():
    await _add([_theft(i, term) for i, term in enumerate(TERMS)] + [PRACTICE_ROBBERY])


async def test_question_is_answered_by_code_with_sources_and_no_case_analysis(client, monkeypatch):
    def no_model():
        raise AssertionError("the case pipeline must not run for a practice question")

    monkeypatch.setattr(analysis_runner, "get_llm_client", no_model)
    await _base()
    chat_id, message = await _ask(client, QUESTION)
    assert message["status"] == "completed", message["error"]
    assert message["result"] is None and not message.get("stale")
    text = message["content"]
    assert "По ч. 2 ст. 158 УК РФ в базе практики 5 приговоров, учтено 5" in text
    assert "среднее 2 г." in text
    assert "Источники" in text
    assert all(f"https://example.invalid/sudact/{i}" in text for i in range(5))
    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["status"] == "ready"


async def test_model_wording_without_new_numbers_is_shown(client, monkeypatch):
    phraser = Phraser("По ч. 2 ст. 158 УК РФ средний срок — 2 г., медиана 2 г.")
    monkeypatch.setattr(analysis_runner, "get_practice_phraser", lambda: phraser)
    await _base()
    _, message = await _ask(client, QUESTION)
    assert message["content"].startswith("По ч. 2 ст. 158 УК РФ средний срок — 2 г.")
    assert "https://example.invalid/sudact/0" in message["content"]
    assert len(phraser.calls) == 1


async def test_model_wording_with_invented_number_is_replaced_by_code(client, monkeypatch):
    phraser = Phraser("Обычно назначают 27 месяцев.")
    monkeypatch.setattr(analysis_runner, "get_practice_phraser", lambda: phraser)
    await _base()
    _, message = await _ask(client, QUESTION)
    assert message["status"] == "completed"
    assert "27 месяцев" not in message["content"]
    assert "среднее 2 г." in message["content"]


async def test_other_questions_still_get_the_case_analysis(client):
    _, message = await _ask(client, "Подготовь проект приговора")
    assert message["status"] == "completed"
    assert message["result"] is not None


async def test_question_with_a_document_is_a_case_analysis(client):
    await _base()
    files = [("files", ("Проект.txt", "Подсудимый похитил ноутбук".encode(), "text/plain"))]
    _, message = await _ask(client, QUESTION, files=files)
    assert message["status"] == "completed"
    assert message["result"] is not None


async def test_without_the_practice_base_the_question_is_not_answered_from_it(client):
    await _base()
    _, message = await _ask(client, QUESTION, use_knowledge_base=False)
    assert message["status"] == "completed"
    assert message["result"] is not None
    assert "Источники" not in (message["content"] or "")


class Llm:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def complete_json(self, system, user):
        self.calls.append((system, user))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def test_phraser_returns_the_model_answer_and_sends_only_the_facts():
    llm = Llm({"answer": "Средний срок — 2 г."})
    wording = await LlmAnswerPhraser(llm).phrase("ч. 2 ст. 158 УК РФ", "среднее 2 г.")
    assert wording == "Средний срок — 2 г."
    system, user = llm.calls[0]
    assert "ч. 2 ст. 158 УК РФ" in user and "среднее 2 г." in user
    assert "Нельзя добавлять" in system


async def test_phraser_failure_or_unusable_reply_is_no_wording():
    for result in (LLMError("LLM ответил 500", status=500), {"answer": 5}, {}, ["answer"]):
        assert await LlmAnswerPhraser(Llm(result)).phrase("ч. 2 ст. 158", "факты") is None


def test_practice_phraser_is_used_only_with_a_real_model(monkeypatch):
    assert analysis_runner.get_practice_phraser() is None  # the fake provider of the tests
    monkeypatch.setattr(analysis_runner.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(analysis_runner, "get_llm_client", lambda: Llm({}))
    assert isinstance(analysis_runner.get_practice_phraser(), LlmAnswerPhraser)

    def not_connected():
        raise LLMError("Языковая модель не подключена")

    monkeypatch.setattr(analysis_runner, "get_llm_client", not_connected)
    assert analysis_runner.get_practice_phraser() is None
