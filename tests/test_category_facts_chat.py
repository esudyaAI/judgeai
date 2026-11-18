"""T45.7 — a category question in the chat answered from the law base by the art. 15 rule."""

from src.services import analysis_runner
from tests.test_practice_facts_chat import _ask
from tests.test_sanction_facts_api import _law_base


async def test_category_question_in_the_chat_is_computed_from_the_imported_sanction(
    client, monkeypatch
):
    def no_model():
        raise AssertionError("the case pipeline must not run for a category question")

    monkeypatch.setattr(analysis_runner, "get_llm_client", no_model)
    await _law_base()
    for use_knowledge_base in (True, False):
        _, message = await _ask(
            client,
            "К какой категории относится ч. 2 ст. 158?",
            use_knowledge_base=use_knowledge_base,
        )
        assert message["status"] == "completed", message["error"]
        assert message["result"] is None
        assert (
            "ч. 2 ст. 158 УК РФ: наибольший срок лишения свободы — 5 г.; "
            "преступление средней тяжести при любой форме вины." in message["content"]
        )
        assert "https://pravo.gov.ru/test-fixture" in message["content"]
        assert message["fact_answer"] == {"kind": "category", "worded_by_model": False}


async def test_category_of_an_unparsed_part_is_not_guessed(client):
    await _law_base()
    _, message = await _ask(client, "Какой тяжести преступление по ч. 1 ст. 159?")
    assert message["status"] == "completed", message["error"]
    assert (
        "санкция ч. 1 ст. 159 УК РФ не разобрана: категорию определить нельзя."
        in (message["content"])
    )
    assert message["fact_answer"]["kind"] == "category"
