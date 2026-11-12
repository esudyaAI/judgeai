"""T15.4: версия справки — отпечаток каталога правил и их оснований из БД.

Отчёт (T14) сохраняет версию справки, по которой сделан вывод; сверка «версия справки совпадает
с отчётом» сводится к сравнению отпечатков. Отпечаток считается только по данным (правила ядра и
связи с нормами из БД), не зависит от даты запроса и меняется при любом изменении основания.
"""

import re
from datetime import UTC, date, datetime
from hashlib import sha256

import pytest
from sqlalchemy import select

from src.db.models import LegalProvision
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import fingerprint, link_rule, rule_basis, rule_catalog

RAW = b"Synthetic criminal code fixture for catalog version, not a real law"
ARTICLES = {"58": "Synthetic article 58.", "62": "Synthetic article 62."}
VERSION = re.compile(r"^sha256:[0-9a-f]{64}$")


def manifest():
    return SnapshotImport.model_validate(
        {
            "act": {"key": "uk-rf", "title": "Synthetic code", "kind": "code"},
            "source_url": "https://pravo.gov.ru/synthetic-version-fixture",
            "raw_sha256": sha256(RAW).hexdigest(),
            "retrieved_at": datetime(2026, 10, 27, tzinfo=UTC),
            "edition_label": "Synthetic edition",
            "full_text": " ".join(ARTICLES.values()),
            "parser_version": "test-fixture-v1",
            "provisions": [
                {"locator": f"article.{n}", "title": f"Article {n}", "body": body, "ordinal": i}
                for i, (n, body) in enumerate(ARTICLES.items())
            ],
        }
    )


async def version_of(db, on=None):
    return (await rule_catalog(db, on))[0]["catalog_version"]


def by_key(items, key):
    return next(item for item in items if item["key"] == key)


def test_fingerprint_is_canonical_and_prefixed():
    first = fingerprint({"a": 1, "b": [date(2020, 5, 1)], "c": "ст. 58"})
    second = fingerprint({"c": "ст. 58", "b": [date(2020, 5, 1)], "a": 1})
    assert first == second
    assert VERSION.match(first)
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})
    assert fingerprint({"d": date(2020, 5, 1)}) != fingerprint({"d": date(2020, 5, 2)})


def test_fingerprint_refuses_values_without_canonical_form():
    with pytest.raises(TypeError):
        fingerprint({"x": object()})


async def test_every_rule_has_basis_version_and_one_catalog_version():
    async with async_session_factory() as db:
        items = await rule_catalog(db)
    versions = {item["catalog_version"] for item in items}
    assert len(versions) == 1 and VERSION.match(versions.pop())
    assert all(VERSION.match(item["basis_version"]) for item in items)
    assert len({item["basis_version"] for item in items}) == len(items)


async def test_version_is_stable_and_independent_of_date():
    async with async_session_factory() as db:
        plain = await rule_catalog(db)
        again = await rule_catalog(db)
        dated = await rule_catalog(db, on=date(2020, 5, 1))
    assert [i["basis_version"] for i in plain] == [i["basis_version"] for i in again]
    assert [i["basis_version"] for i in plain] == [i["basis_version"] for i in dated]
    assert plain[0]["catalog_version"] == dated[0]["catalog_version"]


async def test_linking_changes_only_the_linked_rule():
    async with async_session_factory() as db:
        before = await rule_catalog(db)
        edition, _ = await import_snapshot(db, manifest(), RAW)
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        after = await rule_catalog(db)
    assert before[0]["catalog_version"] != after[0]["catalog_version"]
    changed = by_key(before, "art58.institution"), by_key(after, "art58.institution")
    assert changed[0]["basis_version"] != changed[1]["basis_version"]
    untouched = by_key(before, "art62.part1_mitigation"), by_key(after, "art62.part1_mitigation")
    assert untouched[0]["basis_version"] == untouched[1]["basis_version"]


async def test_verification_and_period_changes_change_version():
    async with async_session_factory() as db:
        edition, _ = await import_snapshot(db, manifest(), RAW)
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        unreviewed = await version_of(db)
        edition.verification_status = "verified"
        await db.flush()
        verified = await version_of(db)
        provision = await db.scalar(
            select(LegalProvision).where(
                LegalProvision.edition_id == edition.id, LegalProvision.locator == "article.58"
            )
        )
        provision.effective_from = date(2014, 1, 1)
        await db.flush()
        dated = await version_of(db)
    assert len({unreviewed, verified, dated}) == 3


async def test_rule_basis_carries_the_same_versions_as_catalog():
    async with async_session_factory() as db:
        items = await rule_catalog(db)
        basis = await rule_basis(db, "art58.institution", on=date(2020, 5, 1))
    listed = by_key(items, "art58.institution")
    assert basis["basis_version"] == listed["basis_version"]
    assert basis["catalog_version"] == listed["catalog_version"]


async def test_rules_api_exposes_versions(client):
    listing = (await client.get("/api/legal/rules")).json()
    dated = (await client.get("/api/legal/rules", params={"on": "2010-05-01"})).json()
    assert VERSION.match(listing["version"])
    assert listing["version"] == dated["version"]
    item = by_key(listing["items"], "art15.category")
    single = (await client.get("/api/legal/rules/art15.category")).json()
    assert single["basis_version"] == item["basis_version"]
    assert single["catalog_version"] == listing["version"]
