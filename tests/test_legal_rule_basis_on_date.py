"""T15.3: основание правила на дату — действие связанной нормы во времени из БД."""

from datetime import UTC, date, datetime
from hashlib import sha256

import pytest
from sqlalchemy import select

from src.db.models import LegalProvision
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import in_force_on, link_rule, rule_basis, rule_catalog

RAW = b"Synthetic criminal code fixture for dated basis, not a real law"
ARTICLES = {"58": "Synthetic article 58.", "86": "Synthetic article 86.", "95": "Synthetic 95."}


def manifest():
    return SnapshotImport.model_validate(
        {
            "act": {"key": "uk-rf", "title": "Synthetic code", "kind": "code"},
            "source_url": "https://pravo.gov.ru/synthetic-dated-fixture",
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


async def verified_edition(db, periods):
    """Import the fixture, mark it verified and set provision periods {locator: (from, to)}."""
    edition, _ = await import_snapshot(db, manifest(), RAW)
    edition.verification_status = "verified"
    for locator, (start, end) in periods.items():
        provision = await db.scalar(
            select(LegalProvision).where(
                LegalProvision.edition_id == edition.id, LegalProvision.locator == locator
            )
        )
        provision.effective_from, provision.effective_to = start, end
    await db.flush()
    return edition


@pytest.mark.parametrize(
    ("start", "end", "on", "expected"),
    [
        (date(2014, 1, 1), None, date(2020, 5, 1), True),
        (date(2014, 1, 1), None, date(2014, 1, 1), True),
        (date(2014, 1, 1), None, date(2013, 12, 31), False),
        (date(2014, 1, 1), date(2019, 1, 1), date(2018, 12, 31), True),
        (date(2014, 1, 1), date(2019, 1, 1), date(2019, 1, 1), False),
        (None, None, date(2020, 5, 1), None),
        (None, date(2019, 1, 1), date(2018, 1, 1), None),
        (None, date(2019, 1, 1), date(2019, 6, 1), False),
    ],
)
def test_in_force_on_uses_start_inclusive_end_exclusive(start, end, on, expected):
    assert in_force_on(start, end, on) is expected


async def test_without_date_behaviour_is_unchanged():
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), None)})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        basis = await rule_basis(db, "art58.institution")
    assert basis["basis_status"] == "verified"
    assert "on" not in basis and "in_force_on" not in basis["references"][0]


async def test_norm_in_force_on_date_is_verified():
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), None)})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        basis = await rule_basis(db, "art58.institution", on=date(2020, 5, 1))
    assert basis["on"] == date(2020, 5, 1)
    assert basis["basis_status"] == "verified"
    assert basis["references"][0]["in_force_on"] is True
    assert basis["missing_norms"] == [] and basis["undated_norms"] == []


async def test_norm_not_yet_or_no_longer_in_force_is_outdated():
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), date(2019, 1, 1))})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        before = await rule_basis(db, "art58.institution", on=date(2010, 5, 1))
        after = await rule_basis(db, "art58.institution", on=date(2019, 1, 1))
    for basis in (before, after):
        assert basis["basis_status"] == "outdated"
        assert basis["references"][0]["in_force_on"] is False
        assert basis["missing_norms"] == [{"act": "uk-rf", "locator": "article.58"}]


async def test_norm_without_period_is_not_claimed_in_force():
    async with async_session_factory() as db:
        edition = await verified_edition(db, {})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        basis = await rule_basis(db, "art58.institution", on=date(2020, 5, 1))
    assert basis["basis_status"] == "period_unknown"
    assert basis["references"][0]["in_force_on"] is None
    assert basis["missing_norms"] == []
    assert basis["undated_norms"] == [{"act": "uk-rf", "locator": "article.58"}]


async def test_one_norm_out_of_force_makes_basis_incomplete():
    async with async_session_factory() as db:
        edition = await verified_edition(
            db,
            {
                "article.86": (date(2014, 1, 1), None),
                "article.95": (date(2021, 1, 1), None),
            },
        )
        await link_rule(db, "art86.expungement", "uk-rf", edition.id, "article.86", "ст. 86")
        await link_rule(db, "art86.expungement", "uk-rf", edition.id, "article.95", "ст. 95")
        basis = await rule_basis(db, "art86.expungement", on=date(2020, 5, 1))
    assert basis["basis_status"] == "incomplete"
    assert basis["missing_norms"] == [{"act": "uk-rf", "locator": "article.95"}]


async def test_rejected_edition_in_force_still_wins():
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), None)})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        edition.verification_status = "rejected"
        await db.flush()
        basis = await rule_basis(db, "art58.institution", on=date(2020, 5, 1))
    assert basis["basis_status"] == "rejected"


async def test_rule_without_references_on_date_has_no_basis():
    async with async_session_factory() as db:
        catalog = await rule_catalog(db, on=date(2020, 5, 1))
    institution = next(item for item in catalog if item["key"] == "art58.institution")
    assert institution["basis_status"] == "no_basis"
    assert institution["on"] == date(2020, 5, 1)


async def test_rules_api_accepts_date(client):
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), None)})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        await db.commit()
    url = "/api/legal/rules/art58.institution"
    old = (await client.get(url, params={"on": "2010-05-01"})).json()
    assert old["basis_status"] == "outdated" and old["on"] == "2010-05-01"
    assert old["references"][0]["in_force_on"] is False
    now = (await client.get(url, params={"on": "2020-05-01"})).json()
    assert now["basis_status"] == "verified"
    listing = (await client.get("/api/legal/rules", params={"on": "2010-05-01"})).json()
    item = next(i for i in listing["items"] if i["key"] == "art58.institution")
    assert item["basis_status"] == "outdated"
    plain = (await client.get(url)).json()
    assert plain["basis_status"] == "verified" and "on" not in plain
    bad = await client.get(url, params={"on": "2020-13-01"})
    assert bad.status_code == 422
