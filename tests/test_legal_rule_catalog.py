from argparse import Namespace
from datetime import UTC, date, datetime
from hashlib import sha256

import pytest
from legal_core.catalog import RULES
from sqlalchemy import func, select

from src.cli.legal_library import run_link_rule
from src.db.models import LegalProvision, LegalRuleReference
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import link_rule, rule_basis, rule_catalog

RAW = b"Synthetic criminal code fixture, not a real law"
ARTICLES = {"58": "Synthetic article 58.", "86": "Synthetic article 86.", "95": "Synthetic 95."}


def code_manifest(raw=RAW, key="uk-rf"):
    return SnapshotImport.model_validate(
        {
            "act": {"key": key, "title": "Synthetic code", "kind": "code"},
            "source_url": "https://pravo.gov.ru/synthetic-fixture",
            "raw_sha256": sha256(raw).hexdigest(),
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


async def imported(db, raw=RAW, key="uk-rf"):
    edition, _ = await import_snapshot(db, code_manifest(raw, key), raw)
    return edition


async def test_rules_without_references_are_listed_as_without_basis():
    async with async_session_factory() as db:
        catalog = await rule_catalog(db)
    assert [item["key"] for item in catalog] == [item.key for item in RULES]
    institution = next(item for item in catalog if item["key"] == "art58.institution")
    assert institution["basis_status"] == "no_basis"
    assert institution["references"] == []
    assert institution["missing_norms"] == [{"act": "uk-rf", "locator": "article.58"}]
    assert institution["needs_legal_review"] is True
    assert institution["not_modelled"]


async def test_link_is_idempotent_and_exposes_provenance():
    async with async_session_factory() as db:
        edition = await imported(db)
        first, created = await link_rule(
            db, "art58.institution", "uk-rf", edition.id, "article.58", "Текст ч. 1 и ч. 3"
        )
        again, created_again = await link_rule(
            db, "art58.institution", "uk-rf", edition.id, "article.58", "Текст ч. 1 и ч. 3"
        )
        await db.commit()
        assert created and not created_again and again.id == first.id
        assert await db.scalar(select(func.count()).select_from(LegalRuleReference)) == 1
        basis = await rule_basis(db, "art58.institution")
    assert basis["basis_status"] == "unreviewed"
    assert basis["missing_norms"] == []
    (reference,) = basis["references"]
    assert reference["act"] == "uk-rf"
    assert reference["locator"] == "article.58"
    assert reference["source_url"] == "https://pravo.gov.ru/synthetic-fixture"
    assert reference["source_sha256"] == sha256(RAW).hexdigest()
    assert reference["verification_status"] == "unreviewed"
    assert reference["edition_label"] == "Synthetic edition"
    assert reference["rationale"] == "Текст ч. 1 и ч. 3"
    assert reference["effective_from"] is None and reference["effective_to"] is None


async def test_status_follows_editions_and_coverage():
    async with async_session_factory() as db:
        edition = await imported(db)
        await link_rule(db, "art86.expungement", "uk-rf", edition.id, "article.86", "ст. 86")
        edition.verification_status = "verified"
        await db.flush()
        partial = await rule_basis(db, "art86.expungement")
        assert partial["basis_status"] == "incomplete"
        assert partial["missing_norms"] == [{"act": "uk-rf", "locator": "article.95"}]
        await link_rule(db, "art86.expungement", "uk-rf", edition.id, "article.95", "ст. 95")
        assert (await rule_basis(db, "art86.expungement"))["basis_status"] == "verified"
        edition.verification_status = "rejected"
        await db.flush()
        assert (await rule_basis(db, "art86.expungement"))["basis_status"] == "rejected"


async def test_reference_to_another_act_does_not_cover_expected_norm():
    async with async_session_factory() as db:
        other = await imported(db, RAW + b"x", key="synthetic-plenum")
        await link_rule(db, "art58.institution", "synthetic-plenum", other.id, "article.58", "п.")
        basis = await rule_basis(db, "art58.institution")
    assert basis["basis_status"] == "unreviewed"
    assert basis["missing_norms"] == [{"act": "uk-rf", "locator": "article.58"}]


@pytest.mark.parametrize(
    ("rule_key", "act", "locator", "rationale", "message"),
    [
        ("art64.exceptional", "uk-rf", "article.58", "x", "rule"),
        ("art58.institution", "uk-rf", "article.999", "x", "provision"),
        ("art58.institution", "upk-rf", "article.58", "x", "act"),
        ("art58.institution", "uk-rf", "article.58", "  ", "rationale"),
    ],
)
async def test_invalid_links_are_rejected(rule_key, act, locator, rationale, message):
    async with async_session_factory() as db:
        edition = await imported(db)
        with pytest.raises(ValueError, match=message):
            await link_rule(db, rule_key, act, edition.id, locator, rationale)
        assert await db.scalar(select(func.count()).select_from(LegalRuleReference)) == 0


async def test_unknown_edition_is_rejected():
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="edition"):
            await link_rule(db, "art58.institution", "uk-rf", 999, "article.58", "x")


async def test_rule_basis_of_unknown_rule_is_none():
    async with async_session_factory() as db:
        assert await rule_basis(db, "art64.exceptional") is None


async def test_rules_api_is_read_only(client):
    async with async_session_factory() as db:
        edition = await imported(db)
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        provision = await db.scalar(
            select(LegalProvision).where(LegalProvision.locator == "article.58")
        )
        provision.effective_from = date(2014, 1, 1)
        await db.commit()
    listing = (await client.get("/api/legal/rules")).json()
    assert len(listing["items"]) == len(RULES)
    assert listing["references"] == 1
    response = await client.get("/api/legal/rules/art58.institution")
    assert response.status_code == 200
    body = response.json()
    assert body["references"][0]["effective_from"] == "2014-01-01"
    assert body["references"][0]["provision_id"] == provision.id
    assert body["references"][0]["edition_id"] == edition.id
    assert (await client.get("/api/legal/rules/art64.exceptional")).status_code == 404
    assert (await client.post("/api/legal/rules", json={})).status_code == 405


async def test_cli_links_rule_once(capsys):
    async with async_session_factory() as db:
        edition = await imported(db)
        await db.commit()
    args = Namespace(
        rule="art58.institution",
        act="uk-rf",
        edition=edition.id,
        locator="article.58",
        rationale="ст. 58",
    )
    await run_link_rule(args)
    await run_link_rule(args)
    out = capsys.readouterr().out
    assert "linked" in out and "already linked" in out and "status=unreviewed" in out
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(LegalRuleReference)) == 1
