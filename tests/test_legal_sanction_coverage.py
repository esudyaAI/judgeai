"""T15.9: охват санкций по статьям в сводке GET /api/legal/rules/coverage — данные БД."""

from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy import select

from src.db.models import LegalEdition, LegalProvision
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.criminal_sanction_import import import_criminal_sanctions
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import article_sanction_states
from tests.test_criminal_sanctions import _manifest, _seed

URL = "/api/legal/rules/coverage"
NEWER_RAW = b"synthetic fixture bytes for sanctions, newer edition"


async def _imported() -> int:
    edition_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, edition_id)
    return edition_id


async def _verify(edition_id: int, start: date | None, end: date | None) -> None:
    async with async_session_factory() as db:
        edition = await db.get(LegalEdition, edition_id)
        edition.verification_status = "verified"
        provision = await db.scalar(
            select(LegalProvision).where(
                LegalProvision.edition_id == edition_id, LegalProvision.locator == "article.158"
            )
        )
        provision.effective_from, provision.effective_to = start, end
        await db.commit()


async def test_without_sanctions_coverage_is_empty(client):
    sanctions = (await client.get(URL)).json()["sanctions"]
    assert sanctions["total_articles"] == 0
    assert sanctions["confirmed"] == sanctions["unconfirmed"] == []
    assert all(keys == [] for keys in sanctions["by_status"].values())


async def test_imported_unreviewed_sanctions_are_not_confirmed(client):
    await _imported()
    body = (await client.get(URL)).json()
    sanctions = body["sanctions"]
    assert sanctions["total_articles"] == 1
    assert sanctions["by_status"]["unreviewed"] == ["158"]
    assert sanctions["confirmed"] == []
    assert sanctions["unconfirmed"] == ["158"]
    assert body["total"] == len(body["confirmed"]) + len(body["unconfirmed"])


async def test_verified_sanctions_follow_period_on_date(client):
    edition_id = await _imported()
    await _verify(edition_id, date(2014, 1, 1), date(2019, 1, 1))
    plain = (await client.get(URL)).json()["sanctions"]
    assert plain["confirmed"] == ["158"]
    in_force = (await client.get(URL, params={"on": "2018-05-01"})).json()["sanctions"]
    assert in_force["confirmed"] == ["158"]
    expired = (await client.get(URL, params={"on": "2019-01-01"})).json()["sanctions"]
    assert expired["confirmed"] == []
    assert expired["by_status"]["outdated"] == ["158"]


async def test_verified_sanctions_without_period_are_not_in_force_on_date(client):
    edition_id = await _imported()
    await _verify(edition_id, None, None)
    dated = (await client.get(URL, params={"on": "2020-01-01"})).json()["sanctions"]
    assert dated["by_status"]["period_unknown"] == ["158"]
    assert dated["confirmed"] == []


async def test_newest_edition_decides_article_status():
    old_id = await _imported()
    await _verify(old_id, date(2014, 1, 1), None)
    data = _manifest().model_dump()
    data["raw_sha256"] = sha256(NEWER_RAW).hexdigest()
    data["retrieved_at"] = datetime(2026, 11, 1, tzinfo=UTC)
    data["edition_label"] = "Synthetic newer edition"
    async with async_session_factory() as db:
        newer, _ = await import_snapshot(db, SnapshotImport.model_validate(data), NEWER_RAW)
        await db.commit()
        await import_criminal_sanctions(db, newer.id)
    async with async_session_factory() as db:
        states = await article_sanction_states(db, date(2020, 1, 1))
    assert [(s.article, s.edition_status, s.in_force) for s in states] == [
        ("158", "unreviewed", None)
    ]


async def test_states_without_date_carry_no_in_force():
    edition_id = await _imported()
    await _verify(edition_id, date(2014, 1, 1), date(2019, 1, 1))
    async with async_session_factory() as db:
        states = await article_sanction_states(db)
    assert [(s.article, s.edition_status, s.in_force) for s in states] == [
        ("158", "verified", None)
    ]
