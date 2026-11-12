"""T15.7: из конкретного замечания результата анализа открыть его правовое основание.

'GET /api/chats/{id}/messages/{mid}/checks/{index}/basis[?on=YYYY-MM-DD]'.

Замечание берётся из сохранённого результата по индексу в 'legal_checks'; основание — то же,
что 'GET /api/legal/rules/{rule_key}' (данные БД, T15.1–T15.4), и сверка версии этого
замечания с текущей справкой (T15.6). Замечание без правила основания не получает ('no_rule'),
выдуманного основания нет. Чужое дело и несуществующий индекс — 404; без результата — 409.
"""

from sqlalchemy import update

from src.db.models import Message
from src.db.session import async_session_factory
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import link_rule
from tests.test_analysis_reference_status import _analysed
from tests.test_auth import account, anonymous, login
from tests.test_legal_rule_catalog_version import RAW, manifest


def _url(chat_id, message, index):
    return f"/api/chats/{chat_id}/messages/{message}/checks/{index}/basis"


def _index_of(result, key):
    return next(i for i, c in enumerate(result["legal_checks"]) if c["rule_key"] == key)


async def test_finding_opens_its_rule_basis(client):
    chat_id, message, result = await _analysed(client)
    index = _index_of(result, "art15.category")
    body = (await client.get(_url(chat_id, message, index))).json()
    assert body["index"] == index
    assert body["check"] == result["legal_checks"][index]
    assert body["reference_status"] == "current"
    assert body["current_basis_version"] == result["legal_checks"][index]["basis_version"]
    assert body["basis"] == (await client.get("/api/legal/rules/art15.category")).json()


async def test_basis_on_date_is_passed_through(client):
    chat_id, message, result = await _analysed(client)
    index = _index_of(result, "art15.category")
    body = (await client.get(_url(chat_id, message, index), params={"on": "2024-03-01"})).json()
    expected = await client.get("/api/legal/rules/art15.category", params={"on": "2024-03-01"})
    assert body["basis"] == expected.json()
    assert body["basis"]["on"] == "2024-03-01"
    bad = await client.get(_url(chat_id, message, index), params={"on": "01.03.2024"})
    assert bad.status_code == 422


async def test_finding_without_rule_has_no_basis(client):
    chat_id, message, _ = await _analysed(client)
    async with async_session_factory() as db:
        stored = await db.get(Message, message)
        analysis = dict(stored.analysis)
        checks = [dict(check) for check in analysis["legal_checks"]]
        checks[0]["rule_key"] = None
        checks[0]["basis_version"] = None
        analysis["legal_checks"] = checks
        await db.execute(update(Message).where(Message.id == message).values(analysis=analysis))
        await db.commit()
    body = (await client.get(_url(chat_id, message, 0))).json()
    assert body["check"]["rule_key"] is None
    assert body["reference_status"] == "no_rule"
    assert body["current_basis_version"] is None
    assert body["basis"] is None


async def test_changed_basis_after_analysis_is_marked(client):
    chat_id, message, result = await _analysed(client)
    index = _index_of(result, "art15.category")
    async with async_session_factory() as db:
        edition, _ = await import_snapshot(db, manifest(), RAW)
        await link_rule(db, "art15.category", "uk-rf", edition.id, "article.58", "ст. 15")
        await db.commit()
    body = (await client.get(_url(chat_id, message, index))).json()
    assert body["reference_status"] == "changed"
    assert body["current_basis_version"] != body["check"]["basis_version"]
    assert body["current_basis_version"] == body["basis"]["basis_version"]
    assert [ref["locator"] for ref in body["basis"]["references"]] == ["article.58"]


async def test_missing_index_message_and_foreign_case(client):
    chat_id, message, result = await _analysed(client)
    total = len(result["legal_checks"])
    assert (await client.get(_url(chat_id, message, total))).status_code == 404
    assert (await client.get(_url(chat_id, message, -1))).status_code == 404
    assert (await client.get(_url(chat_id, message - 1, 0))).status_code == 409
    assert (await client.get(_url(chat_id, message + 100, 0))).status_code == 404
    other = (await client.post("/api/chats", json={"title": None})).json()["id"]
    assert (await client.get(_url(other, message, 0))).status_code == 404
    await account("mallory")
    async with anonymous() as mallory:
        await login(mallory, "mallory")
        response = await mallory.get(_url(chat_id, message, 0))
    assert response.status_code == 404
