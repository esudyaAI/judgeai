"""T15.11: результат анализа помнит версию данных санкций, по которой сделаны замечания.

Версия — отпечаток T15.10 из БД (`sanctions.version` сводки `GET /api/legal/rules/coverage`),
прочитанный в момент анализа в той же сессии, что санкции. Сверка
`GET /api/chats/{id}/messages/{mid}/reference-status` получает блок `sanctions`:
`current`/`changed`/`unknown`; результат, сохранённый до T15.11, — `unknown`, а не «совпадает».
Версия каталога правил (T15.5/T15.6) от этого не меняется.
"""

from sqlalchemy import update

from src.db.models import Message
from src.db.session import async_session_factory
from src.schemas.analysis import CaseAnalysis
from src.services.legal_rule_catalog import ReferenceVersions, reference_versions, sanctions_version
from tests.test_analysis_reference_status import _analysed, _url
from tests.test_analysis_reference_version import GUILT, REFERENCE, _analyse
from tests.test_legal_sanction_coverage import URL, _imported
from tests.test_statute_sanction_analysis import PART_2

SANCTIONS = "sha256:" + "5" * 64


async def test_reference_versions_include_sanctions_version():
    async with async_session_factory() as db:
        versions = await reference_versions(db)
        assert versions.sanctions == await sanctions_version(db)
    await _imported()
    async with async_session_factory() as db:
        changed = await reference_versions(db)
        assert changed.sanctions == await sanctions_version(db)
    assert changed.sanctions != versions.sanctions
    assert changed.catalog == versions.catalog


def test_analysis_without_reference_has_no_sanctions_version():
    assert _analyse(PART_2, GUILT).sanctions_version is None


def test_analysis_stamps_sanctions_version():
    reference = ReferenceVersions(
        catalog=REFERENCE.catalog, rules=REFERENCE.rules, sanctions=SANCTIONS
    )
    result = _analyse(PART_2, GUILT, reference=reference)
    assert result.sanctions_version == SANCTIONS
    assert result.reference_version == REFERENCE.catalog


def test_reference_without_sanctions_version_invents_none():
    assert _analyse(PART_2, GUILT, reference=REFERENCE).sanctions_version is None


def test_results_stored_before_sanctions_version_still_load():
    reference = ReferenceVersions(catalog=REFERENCE.catalog, sanctions=SANCTIONS)
    stored = _analyse(PART_2, GUILT, reference=reference).model_dump(mode="json")
    stored.pop("sanctions_version")
    assert CaseAnalysis.model_validate(stored).sanctions_version is None


async def test_completed_analysis_stores_current_sanctions_version(client):
    await _imported()
    chat_id, message, result = await _analysed(client)
    current = (await client.get(URL)).json()["sanctions"]["version"]
    assert result["sanctions_version"] == current
    status = (await client.get(_url(chat_id, message))).json()
    assert status["sanctions"] == {
        "status": "current",
        "stored_version": current,
        "current_version": current,
    }


async def test_sanctions_imported_after_analysis_are_reported(client):
    chat_id, message, result = await _analysed(client)
    await _imported()
    status = (await client.get(_url(chat_id, message))).json()
    current = (await client.get(URL)).json()["sanctions"]["version"]
    assert status["sanctions"]["status"] == "changed"
    assert status["sanctions"]["stored_version"] == result["sanctions_version"]
    assert status["sanctions"]["current_version"] == current != result["sanctions_version"]
    # the rule catalog did not change: its status and the findings stay current
    assert status["status"] == "current"
    assert status["changed_rules"] == []


async def test_result_stored_before_sanctions_version_is_unknown(client):
    chat_id, message, _ = await _analysed(client)
    async with async_session_factory() as db:
        stored = await db.get(Message, message)
        analysis = dict(stored.analysis)
        analysis.pop("sanctions_version")
        await db.execute(update(Message).where(Message.id == message).values(analysis=analysis))
        await db.commit()
    status = (await client.get(_url(chat_id, message))).json()
    assert status["sanctions"]["status"] == "unknown"
    assert status["sanctions"]["stored_version"] is None
    assert status["status"] == "current"
