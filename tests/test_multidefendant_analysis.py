"""Live API path: global fake-model facts must not mix two convicted people."""

TEXT = (
    "ФИО1, ранее не судимый. ФИО2, ранее отбывал лишение свободы.\n"
    "УСТАНОВИЛ:\nСуд признаёт у ФИО1 смягчающим явку с повинной.\n\n"
    "У ФИО2 суд установил опасный рецидив преступлений.\nПРИГОВОРИЛ:\n"
    "ФИО1 признать виновным по ч. 1 ст. 158 УК РФ и назначить наказание "
    "в виде лишения свободы на срок 1 год.\n"
    "ФИО2 признать виновным по ч. 2 ст. 161 УК РФ и назначить наказание "
    "в виде лишения свободы на срок 4 года."
)


async def test_api_returns_isolated_personal_sentences_and_recidivism(client):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    response = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь обоих осуждённых", "use_knowledge_base": "false"},
        files=[("files", ("synthetic.txt", TEXT.encode(), "text/plain"))],
    )
    assert response.status_code == 202, response.text
    message_id = response.json()["assistant_message"]["id"]
    reply = (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()
    assert reply["status"] == "completed", reply["error"]
    result = reply["result"]
    assert len(result["defendants"]) == 2 and not result["legal_checks"]
    first, second = result["defendants"]
    assert first["imposed_sentence"]["counts"][0]["imprisonment_months"] == 12
    assert second["imposed_sentence"]["counts"][0]["imprisonment_months"] == 48
    assert first["mitigating"] and not second["mitigating"]
    assert (
        next(c for c in first["legal_checks"] if c["norm"] == "ст. 18 УК РФ")["recidivism_input"]
        == "none"
    )
    assert (
        next(c for c in second["legal_checks"] if c["norm"] == "ст. 18 УК РФ")["recidivism_input"]
        == "dangerous"
    )
    # Persisted result is identical on a subsequent GET, not assembled only for this response.
    assert (await client.get(f"/api/chats/{chat_id}/messages/{message_id}")).json()[
        "result"
    ] == result


async def test_precedent_endpoint_requires_person_instead_of_mixing_facts(client, monkeypatch):
    from src.api.precedents import get_embedder
    from src.main import app
    from tests.fixtures.fake_embedder import HashingEmbedder

    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    try:
        chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
        await client.post(
            f"/api/chats/{chat_id}/messages",
            data={"content": "Проверь", "use_knowledge_base": "false"},
            files=[("files", ("synthetic.txt", TEXT.encode(), "text/plain"))],
        )
        common = await client.get(f"/api/chats/{chat_id}/precedents")
        assert common.status_code == 200 and common.json()["query"] is None
        assert "несколько" in common.json()["note"]
        second = await client.get(f"/api/chats/{chat_id}/precedents?defendant=2")
        assert second.status_code == 200 and second.json()["query"]["recidivism"] == "dangerous"
        assert second.json()["query"]["qualifications"] == ["ч. 2 ст. 161 УК РФ"]
        assert (await client.get(f"/api/chats/{chat_id}/precedents?defendant=3")).status_code == 422
    finally:
        app.dependency_overrides.pop(get_embedder, None)
