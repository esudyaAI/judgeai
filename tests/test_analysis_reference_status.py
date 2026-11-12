"""T15.6: изменилась ли справка после анализа.

`GET /api/chats/{id}/messages/{mid}/reference-status`.

Сохранённые в результате версии (T15.5) сверяются с текущими отпечатками справки из БД (T15.4).
Чужое дело — 404; сообщение без результата анализа — 409; результат до T15.5 — `unknown`.
"""

from sqlalchemy import update

from src.db.models import Message
from src.db.session import async_session_factory
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import link_rule
from tests.test_auth import account, anonymous, login
from tests.test_legal_rule_catalog_version import RAW, manifest

DRAFT = ("files", ("Проект.txt", "Подсудимый действовал умышленно.".encode(), "text/plain"))


async def _analysed(client):
    chat_id = (await client.post("/api/chats", json={"title": None})).json()["id"]
    sent = await client.post(
        f"/api/chats/{chat_id}/messages", data={"content": "Проверь проект"}, files=[DRAFT]
    )
    message = sent.json()["assistant_message"]["id"]
    polled = (await client.get(f"/api/chats/{chat_id}/messages/{message}")).json()
    assert polled["status"] == "completed", polled["error"]
    return chat_id, message, polled["result"]


def _url(chat_id, message):
    return f"/api/chats/{chat_id}/messages/{message}/reference-status"


async def test_fresh_analysis_matches_current_reference(client):
    chat_id, message, result = await _analysed(client)
    status = (await client.get(_url(chat_id, message))).json()
    assert status["status"] == "current"
    assert status["stored_version"] == result["reference_version"]
    assert status["current_version"] == (await client.get("/api/legal/rules")).json()["version"]
    assert status["changed_rules"] == []
    assert len(status["checks"]) == len(result["legal_checks"])
    for check, stored in zip(status["checks"], result["legal_checks"], strict=True):
        assert check["rule_key"] == stored["rule_key"]
        assert check["status"] == ("current" if stored["rule_key"] else "no_rule")


async def test_new_basis_after_analysis_is_reported(client):
    chat_id, message, result = await _analysed(client)
    keys = {check["rule_key"] for check in result["legal_checks"]}
    assert "art15.category" in keys
    async with async_session_factory() as db:
        edition, _ = await import_snapshot(db, manifest(), RAW)
        await link_rule(db, "art15.category", "uk-rf", edition.id, "article.58", "ст. 15")
        await db.commit()
    status = (await client.get(_url(chat_id, message))).json()
    assert status["status"] == "changed"
    assert status["changed_rules"] == ["art15.category"]
    changed = [c for c in status["checks"] if c["rule_key"] == "art15.category"]
    assert changed and all(c["status"] == "changed" for c in changed)
    assert all(c["basis_version"] != c["current_basis_version"] for c in changed)


async def test_result_stored_before_versions_is_unknown(client):
    chat_id, message, _ = await _analysed(client)
    async with async_session_factory() as db:
        stored = await db.get(Message, message)
        analysis = dict(stored.analysis)
        analysis.pop("reference_version")
        analysis["legal_checks"] = [
            {k: v for k, v in check.items() if k != "basis_version"}
            for check in analysis["legal_checks"]
        ]
        await db.execute(update(Message).where(Message.id == message).values(analysis=analysis))
        await db.commit()
    status = (await client.get(_url(chat_id, message))).json()
    assert status["status"] == "unknown"
    assert status["stored_version"] is None
    assert {c["status"] for c in status["checks"]} <= {"unknown", "no_rule"}


async def test_message_without_analysis_is_409(client):
    chat_id, message, _ = await _analysed(client)
    response = await client.get(_url(chat_id, message - 1))  # the user's request message
    assert response.status_code == 409


async def test_unknown_message_and_foreign_case_are_404(client):
    chat_id, message, _ = await _analysed(client)
    assert (await client.get(_url(chat_id, message + 100))).status_code == 404
    other = (await client.post("/api/chats", json={"title": None})).json()["id"]
    assert (await client.get(_url(other, message))).status_code == 404
    await account("mallory")
    async with anonymous() as mallory:
        await login(mallory, "mallory")
        response = await mallory.get(_url(chat_id, message))
    assert response.status_code == 404
