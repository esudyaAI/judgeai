"""T15.10: версия данных санкций в сводке справки — отпечаток из БД, не зависит от даты."""

from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy import select, update

from src.db.models import CriminalArticleSanction, LegalProvision
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.criminal_sanction_import import import_criminal_sanctions
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import fingerprint, sanctions_version
from tests.test_criminal_sanctions import _manifest
from tests.test_legal_sanction_coverage import NEWER_RAW, URL, _imported, _verify


async def _version(client, **params) -> str:
    return (await client.get(URL, params=params)).json()["sanctions"]["version"]


async def _import_newer() -> int:
    data = _manifest().model_dump()
    data["raw_sha256"] = sha256(NEWER_RAW).hexdigest()
    data["retrieved_at"] = datetime(2026, 11, 1, tzinfo=UTC)
    data["edition_label"] = "Synthetic newer edition"
    async with async_session_factory() as db:
        newer, _ = await import_snapshot(db, SnapshotImport.model_validate(data), NEWER_RAW)
        await db.commit()
        await import_criminal_sanctions(db, newer.id)
        return newer.id


async def _raise_max(edition_id: int) -> None:
    """Shift the upper bounds of one edition's sanctions (a changed reading of the same text)."""
    provisions = select(LegalProvision.id).where(LegalProvision.edition_id == edition_id)
    async with async_session_factory() as db:
        await db.execute(
            update(CriminalArticleSanction)
            .where(
                CriminalArticleSanction.provision_id.in_(provisions),
                CriminalArticleSanction.max_value.is_not(None),
            )
            .values(max_value=CriminalArticleSanction.max_value + 1)
        )
        await db.commit()


async def test_without_sanctions_version_is_fingerprint_of_nothing(client):
    version = await _version(client)
    assert version == fingerprint([])
    assert await _version(client, on="2018-05-01") == version


async def test_version_is_stable_and_does_not_depend_on_date(client):
    await _imported()
    version = await _version(client)
    assert version.startswith("sha256:")
    assert version != fingerprint([])
    assert await _version(client) == version
    assert await _version(client, on="2018-05-01") == version
    assert await _version(client, on="2030-01-01") == version
    async with async_session_factory() as db:
        assert await sanctions_version(db) == version


async def test_rule_catalog_version_is_unchanged_by_sanctions(client):
    before = (await client.get(URL)).json()["version"]
    await _imported()
    body = (await client.get(URL)).json()
    assert body["version"] == before
    assert body["sanctions"]["version"] != before


async def test_review_status_changes_version(client):
    edition_id = await _imported()
    before = await _version(client)
    await _verify(edition_id, None, None)
    assert await _version(client) != before


async def test_period_of_force_changes_version(client):
    edition_id = await _imported()
    await _verify(edition_id, None, None)
    before = await _version(client)
    await _verify(edition_id, date(2014, 1, 1), None)
    assert await _version(client) != before


async def test_changed_sanction_bounds_change_version(client):
    edition_id = await _imported()
    before = await _version(client)
    await _raise_max(edition_id)
    assert await _version(client) != before


async def test_repeated_import_keeps_version(client):
    edition_id = await _imported()
    before = await _version(client)
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, edition_id)
    assert await _version(client) == before


async def test_only_newest_edition_counts(client):
    old_id = await _imported()
    only_old = await _version(client)
    await _import_newer()
    current = await _version(client)
    assert current != only_old
    await _raise_max(old_id)
    assert await _version(client) == current
