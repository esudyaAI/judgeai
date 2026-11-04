import io
from zipfile import ZipFile

from src.db.models import Message
from src.db.session import async_session_factory
from tests.test_auth import account, anonymous, login


async def analysed(client):
    chat = (await client.post("/api/chats", json={"title": "Synthetic report"})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat}/messages",
        data={"content": "Проверь", "use_knowledge_base": "false"},
        files=[
            ("files", ("synthetic.txt", "Синтетические материалы дела.".encode(), "text/plain"))
        ],
    )
    return chat, sent.json()["assistant_message"]["id"]


async def test_report_is_idempotent_owned_and_contains_a_real_docx(client):
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/reports"
    created = await client.post(path)
    assert created.status_code == 201, created.text
    report = created.json()
    assert report["version"] == 1
    again = await client.post(path)
    assert again.status_code == 200 and again.json()["id"] == report["id"]
    detail = (await client.get(f"/api/reports/{report['id']}")).json()
    assert detail["snapshot"]["materials"][0]["text"] == "Синтетические материалы дела."
    assert detail["snapshot"]["materials"][0]["original_sha256"]
    assert "stored_path" not in str(detail)
    assert detail["snapshot"]["human_review"]["status"] == "not_reviewed"
    assert detail["snapshot"]["analysis"]["provenance"]["llm"]["mode"] == "synthetic"
    assert detail["snapshot"]["materials"][0]["hash_captured_at"] == "analysis"
    download = await client.get(f"/api/reports/{report['id']}/docx")
    assert download.status_code == 200
    assert "no-store" in download.headers["cache-control"]
    with ZipFile(io.BytesIO(download.content)) as document:
        xml = document.read("word/document.xml").decode()
        assert "Отчёт о проверке" in xml and "Не проверено человеком" in xml
    await account("report-stranger")
    async with anonymous() as stranger:
        await login(stranger, "report-stranger")
        assert (await stranger.get("/api/reports")).json() == []
        for suffix in ("", "/docx"):
            assert (await stranger.get(f"/api/reports/{report['id']}{suffix}")).status_code == 404
        assert (await stranger.post(path)).status_code == 404
    assert len((await client.get("/api/reports")).json()) == 1


async def test_saved_report_and_bytes_do_not_follow_mutable_source(client):
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/reports"
    first = (await client.post(path)).json()
    url = f"/api/reports/{first['id']}"
    snapshot = (await client.get(url)).json()
    artifact = (await client.get(url + "/docx")).content
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        row.analysis = {
            **row.analysis,
            "fabula": "Changed later",
            "engine_version": "future-engine",
        }
        await db.commit()
    second = (await client.post(path)).json()
    assert second["version"] == 2 and second["id"] != first["id"]
    assert (await client.get(url)).json() == snapshot
    assert (await client.get(url + "/docx")).content == artifact
    assert len((await client.get(f"/api/reports?chat_id={chat}")).json()) == 2


async def test_report_refuses_busy_empty_and_incompatible_sources(client):
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/reports"
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        original = row.analysis
        row.status = "running"
        await db.commit()
    assert (await client.post(path)).status_code == 409
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        row.status = "completed"
        row.analysis = {**original, "schema_version": 999}
        await db.commit()
    assert (await client.post(path)).status_code == 409
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        row.analysis = {"schema_version": 1}
        await db.commit()
    assert (await client.post(path)).status_code == 409
    assert (await client.get("/api/reports")).json() == []


async def test_export_failure_rolls_back_and_saved_download_never_calls_builder(
    client, monkeypatch
):
    from src.infrastructure.report_docx import DocxReportExporter

    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/reports"
    render = DocxReportExporter.render

    async def fail(*args, **kwargs):
        raise RuntimeError("sensitive provider detail")

    monkeypatch.setattr(DocxReportExporter, "render", fail)
    failed = await client.post(path)
    assert failed.status_code == 503 and "sensitive" not in failed.text
    assert (await client.get("/api/reports")).json() == []
    monkeypatch.setattr(DocxReportExporter, "render", render)
    created = (await client.post(path)).json()
    monkeypatch.setattr(DocxReportExporter, "render", fail)
    assert (await client.post(path)).status_code == 200
    assert (await client.get(f"/api/reports/{created['id']}/docx")).status_code == 200


async def test_missing_original_is_explicit_and_material_changes_refuse_new_snapshot(client):
    from pathlib import Path

    from sqlalchemy import select

    from src.db.models import Attachment

    chat, message = await analysed(client)
    async with async_session_factory() as db:
        attachment = await db.scalar(
            select(Attachment).join(Message).where(Message.chat_id == chat)
        )
        Path(attachment.stored_path).unlink()
        attachment_id = attachment.id
    path = f"/api/chats/{chat}/messages/{message}/reports"
    response = await client.post(path)
    assert response.status_code == 201
    detail = (await client.get(f"/api/reports/{response.json()['id']}")).json()
    assert detail["snapshot"]["materials"][0]["original_sha256"]
    assert detail["snapshot"]["materials"][0]["hash_captured_at"] == "analysis"
    assert any("недоступен" in item for item in detail["snapshot"]["limitations"])
    async with async_session_factory() as db:
        attachment = await db.get(Attachment, attachment_id)
        attachment.extracted_text = "changed source"
        await db.commit()
    assert (await client.post(path)).status_code == 409
    assert (await client.get(f"/api/reports/{response.json()['id']}/docx")).status_code == 200


async def test_report_requires_csrf_and_cascade_deletes_only_target_case(client):
    chat, message = await analysed(client)
    other_chat, other_message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/reports"
    token = client.headers.pop("X-CSRF-Token")
    assert (await client.post(path)).status_code == 403
    client.headers["X-CSRF-Token"] = token
    first = (await client.post(path)).json()
    second = (await client.post(f"/api/chats/{other_chat}/messages/{other_message}/reports")).json()
    assert (await client.delete(f"/api/chats/{chat}")).status_code == 200
    assert (await client.get(f"/api/reports/{first['id']}")).status_code == 404
    assert (await client.get(f"/api/reports/{second['id']}/docx")).status_code == 200


async def test_report_integrity_is_checked_before_download(client):
    from uuid import UUID

    from src.db.reports import CaseReport

    chat, message = await analysed(client)
    report = (await client.post(f"/api/chats/{chat}/messages/{message}/reports")).json()
    async with async_session_factory() as db:
        row = await db.get(CaseReport, UUID(report["id"]))
        row.docx_data = b"tampered"
        await db.commit()
    assert (await client.get(f"/api/reports/{report['id']}/docx")).status_code == 409


async def test_account_export_includes_saved_snapshots_without_binary_or_paths(client):
    chat, message = await analysed(client)
    created = (await client.post(f"/api/chats/{chat}/messages/{message}/reports")).json()
    exported = await client.get("/api/account/export")
    assert exported.status_code == 200
    report = exported.json()["reports"][0]
    assert report["id"] == created["id"]
    assert report["snapshot"]["materials"][0]["text"] == "Синтетические материалы дела."
    assert "stored_path" not in exported.text and "docx_data" not in exported.text


def test_docx_copies_imposed_values_and_quotes_without_running_calculations():
    from datetime import UTC, datetime

    from src.infrastructure.report_docx import build_report_docx

    artifact = build_report_docx(
        {
            "analysis": {
                "fabula": "Синтетический результат",
                "engine_version": "saved-engine",
                "imposed_sentence": {
                    "final": "сохранённое наказание",
                    "probation_months": 37,
                    "conditional": True,
                    "fine_credits": [
                        {
                            "scope": "final",
                            "original_amount": 12345,
                            "reduced_amount": 6789,
                            "quote": "Точная цитата о зачёте",
                        }
                    ],
                },
                "legal_checks": [
                    {
                        "norm": "ст. X",
                        "status": "insufficient_data",
                        "explanation": "Сохранённое обоснование",
                        "source": "saved-source",
                        "evidence": ["Точная цитата из проекта"],
                    }
                ],
                "practice": {
                    "total": 9,
                    "with_term": 7,
                    "enough_data": False,
                    "median_months": 23,
                    "excluded": 4,
                },
            },
            "human_review": {"status": "not_reviewed"},
            "limitations": ["Область не проверена"],
        },
        5,
        datetime(2026, 11, 4, tzinfo=UTC),
    )
    with ZipFile(io.BytesIO(artifact)) as document:
        xml = document.read("word/document.xml").decode()
    for value in (
        "сохранённое наказание",
        "37",
        "12345",
        "6789",
        "Точная цитата о зачёте",
        "Точная цитата из проекта",
        "Сохранённое обоснование",
        "saved-source",
        "Размер выборки n: 9",
        "Медиана, мес.: 23",
        "Область не проверена",
    ):
        assert value in xml


async def test_legacy_report_never_invents_current_provider_or_norm_versions(client):
    chat, message = await analysed(client)
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        row.analysis = {
            key: value
            for key, value in row.analysis.items()
            if key not in {"extraction", "provenance"}
        }
        await db.commit()
    created = await client.post(f"/api/chats/{chat}/messages/{message}/reports")
    assert created.status_code == 201
    snapshot = (await client.get(f"/api/reports/{created.json()['id']}")).json()["snapshot"]
    assert not snapshot["analysis"].get("provenance")
    assert snapshot["materials"][0]["hash_captured_at"] == "report_creation"
    assert any("неизвестны" in text for text in snapshot["limitations"])
    assert any("старом результате нет хешей" in text for text in snapshot["limitations"])
