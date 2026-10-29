import pytest

from src.services import llm_client


async def _new_chat(client, title="Кража") -> int:
    r = await client.post("/api/chats", json={"title": title})
    assert r.status_code == 201
    assert r.json()["status"] == "draft"
    return r.json()["id"]


def _txt(name="Обвинительное заключение.txt", body="Подсудимый похитил ноутбук"):
    return ("files", (name, body.encode("utf-8"), "text/plain"))


async def test_full_analysis_flow(client):
    chat_id = await _new_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Подготовь проект приговора"},
        files=[
            _txt(
                body="Подсудимый похитил ноутбук. Суд признаёт явку с повинной "
                "смягчающим обстоятельством. Отягчающих обстоятельств не установлено."
            )
        ],
    )
    assert r.status_code == 202
    body = r.json()
    # The response is sent before the analysis runs.
    assert body["assistant_message"]["status"] == "pending"
    assert body["user_message"]["attachments"][0]["filename"] == "Обвинительное заключение.txt"
    msg_id = body["assistant_message"]["id"]

    r = await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")
    msg = r.json()
    assert msg["status"] == "completed", msg["error"]
    assert msg["stage"] is None
    result = msg["result"]
    assert result["schema_version"] == 1
    assert result["qualification"]["article"] == "п. «в» ч. 2 ст. 158 УК РФ"
    # ч. 1 ст. 62 limit is computed in code: 2/3 of 60 months
    assert result["scale"]["limit_months"] == 40
    assert result["scale"]["within_sanction"] is True
    assert result["stats"]["documents"] == 1
    assert any("не сверен" in w for w in result["warnings"])

    chats = (await client.get("/api/chats")).json()
    assert chats[0]["id"] == chat_id and chats[0]["status"] == "ready"
    assert chats[0]["title"] == "Кража"  # an explicit title is never overwritten


async def test_untitled_case_gets_qualification_as_title(client):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    await client.post(f"/api/chats/{chat_id}/messages", files=[_txt()])
    assert (await client.get(f"/api/chats/{chat_id}")).json()[
        "title"
    ] == "п. «в» ч. 2 ст. 158 УК РФ"


async def test_updated_at_moves_and_list_is_ordered(client):
    first = await _new_chat(client, "первое")
    second = await _new_chat(client, "второе")
    before = (await client.get(f"/api/chats/{first}")).json()["updated_at"]
    await client.post(f"/api/chats/{first}/messages", data={"content": "вопрос"})
    after = (await client.get(f"/api/chats/{first}")).json()["updated_at"]
    assert after > before
    ids = [c["id"] for c in (await client.get("/api/chats")).json()]
    assert ids.index(first) < ids.index(second)


async def test_llm_failure_marks_message_failed(client, monkeypatch):
    class Broken:
        async def complete_json(self, system, user):
            raise llm_client.LLMError("LLM ответил 500")

    monkeypatch.setattr("src.services.analysis_runner.get_llm_client", lambda: Broken())
    chat_id = await _new_chat(client)
    r = await client.post(f"/api/chats/{chat_id}/messages", data={"content": "вопрос"})
    msg = (
        await client.get(f"/api/chats/{chat_id}/messages/{r.json()['assistant_message']['id']}")
    ).json()
    assert msg["status"] == "failed" and msg["error"] == "LLM ответил 500" and msg["result"] is None
    assert (await client.get(f"/api/chats/{chat_id}")).json()["status"] == "failed"


async def test_health_reports_503_when_database_is_down(client, monkeypatch):
    class BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *_args):
            raise RuntimeError("the database system is in recovery mode")

    monkeypatch.setattr("src.main.async_session_factory", lambda: BrokenSession())
    r = await client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": "unavailable"}


async def test_health_confirms_database_with_200(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


async def test_invalid_llm_output_is_retried_then_failed(client, monkeypatch):
    calls = []

    class Garbage:
        async def complete_json(self, system, user):
            calls.append(1)
            return {"not": "the schema"}

    monkeypatch.setattr("src.services.analysis_runner.get_llm_client", lambda: Garbage())
    chat_id = await _new_chat(client)
    r = await client.post(f"/api/chats/{chat_id}/messages", data={"content": "вопрос"})
    msg = (
        await client.get(f"/api/chats/{chat_id}/messages/{r.json()['assistant_message']['id']}")
    ).json()
    assert len(calls) == 2
    assert msg["status"] == "failed" and "схеме" in msg["error"]


async def test_extraction_status_is_reported(client, monkeypatch):
    from src.services.document_parser import ExtractedDocument
    from tests_pdf.fixtures import pdf

    async def failed_extraction(path):
        return ExtractedDocument("", None, "error")

    monkeypatch.setattr("src.services.analysis_runner.extract_document", failed_extraction)
    chat_id = await _new_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Explain the extraction warning"},
        files=[("files", ("Протокол.pdf", pdf(), "application/pdf"))],
    )
    msgs = (await client.get(f"/api/chats/{chat_id}/messages")).json()
    att = msgs[0]["attachments"][0]
    assert att["extraction_status"] == "error"
    result = next(m for m in msgs if m["role"] == "assistant")["result"]
    assert any("Протокол.pdf" in w for w in result["warnings"])
    assert r.status_code == 202


@pytest.mark.parametrize(
    ("files", "data", "code"),
    [
        ([("files", ("scan.exe", b"x", "application/octet-stream"))], {}, 415),
        ([], {}, 422),
    ],
)
async def test_upload_validation(client, files, data, code):
    chat_id = await _new_chat(client)
    r = await client.post(f"/api/chats/{chat_id}/messages", data=data, files=files or None)
    assert r.status_code == code
    assert (await client.get(f"/api/chats/{chat_id}/messages")).json() == []


async def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr("src.services.file_reader.settings.UPLOAD_MAX_MB", 1)
    chat_id = await _new_chat(client)
    big = ("files", ("big.txt", b"a" * (1024 * 1024 + 1), "text/plain"))
    r = await client.post(f"/api/chats/{chat_id}/messages", files=[big])
    assert r.status_code == 413


async def test_missing_chat_and_message(client):
    assert (await client.get("/api/chats/999")).status_code == 404
    chat_id = await _new_chat(client)
    assert (await client.get(f"/api/chats/{chat_id}/messages/999")).status_code == 404


async def test_interrupted_analyses_are_failed_on_startup(client):
    from sqlalchemy import update

    from src.db.models import Message
    from src.db.session import async_session_factory
    from src.services.analysis_runner import INTERRUPTED_ERROR, fail_interrupted_analyses

    chat_id = await _new_chat(client)
    r = await client.post(f"/api/chats/{chat_id}/messages", data={"content": "вопрос"})
    msg_id = r.json()["assistant_message"]["id"]
    async with async_session_factory() as db:
        await db.execute(
            update(Message).where(Message.id == msg_id).values(status="running", stage="qualifying")
        )
        await db.commit()

    assert await fail_interrupted_analyses() == 1
    msg = (await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")).json()
    assert (msg["status"], msg["stage"], msg["error"]) == ("failed", None, INTERRUPTED_ERROR)


async def test_rejected_second_file_cleans_first_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr("src.services.file_reader.settings.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("src.services.file_reader.settings.UPLOAD_MAX_MB", 1)
    chat_id = await _new_chat(client)
    response = await client.post(
        f"/api/chats/{chat_id}/messages",
        files=[_txt(), ("files", ("big.txt", b"a" * (1024 * 1024 + 1), "text/plain"))],
    )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []
    assert (await client.get(f"/api/chats/{chat_id}/messages")).json() == []


async def test_fake_analysis_is_labelled_as_development(client):
    chat_id = await _new_chat(client)
    await client.post(f"/api/chats/{chat_id}/messages", data={"content": "Synthetic verdict"})
    messages = (await client.get(f"/api/chats/{chat_id}/messages")).json()
    assert any("режим разработки" in w.lower() for w in messages[-1]["result"]["warnings"])


async def test_operative_part_of_uploaded_draft_is_read_per_count(client):
    from tests.fixtures.synthetic_verdicts import MULTI_COUNT

    chat_id = await _new_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Проверь проект"},
        files=[_txt("Проект приговора.txt", MULTI_COUNT)],
    )
    msg_id = r.json()["assistant_message"]["id"]
    result = (await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")).json()["result"]
    sentence = result["imposed_sentence"]
    assert [c["imprisonment_months"] for c in sentence["counts"]] == [30, 20]
    assert sentence["aggregation_rule"] == "ч. 3 ст. 69 УК РФ"
    norms = [c["norm"] for c in result["legal_checks"]]
    # No sanctions are imported in the test database: every count is explicitly unchecked.
    assert "Назначенное наказание · п. «г» ч. 3 ст. 158 УК РФ" in norms
    assert "Окончательное наказание (ч. 3 ст. 69 УК РФ)" in norms


async def test_analysis_stages_follow_the_order_of_the_work(client, monkeypatch):
    import src.services.analysis_runner as runner

    seen = []
    original = runner._set_stage

    async def record(message_id, *, status="running", stage=None):
        seen.append(stage)
        await original(message_id, status=status, stage=stage)

    monkeypatch.setattr(runner, "_set_stage", record)
    chat_id = await _new_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/messages",
        data={"content": "Подготовь проект приговора"},
        files=[_txt()],
    )
    msg_id = r.json()["assistant_message"]["id"]
    msg = (await client.get(f"/api/chats/{chat_id}/messages/{msg_id}")).json()
    assert msg["status"] == "completed", msg["error"]
    assert [stage for stage in seen if stage] == [
        "extracting",
        "checking",
        "searching",
        "recommending",
    ]
