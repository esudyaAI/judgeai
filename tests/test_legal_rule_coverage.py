"""T15.8: GET /api/legal/rules/coverage — область поддержки справки из БД."""

from datetime import date

from src.db.session import async_session_factory
from src.services.legal_rule_catalog import link_rule, rule_coverage
from tests.test_legal_rule_basis_on_date import verified_edition

URL = "/api/legal/rules/coverage"


async def test_without_links_no_rule_is_confirmed(client):
    listing = (await client.get("/api/legal/rules")).json()
    coverage = (await client.get(URL)).json()
    keys = sorted(item["key"] for item in listing["items"])
    assert coverage["version"] == listing["version"]
    assert coverage["on"] is None
    assert coverage["total"] == len(keys)
    assert coverage["by_status"]["no_basis"] == keys
    assert coverage["confirmed"] == []
    assert coverage["unconfirmed"] == keys
    assert coverage["needs_legal_review"] == sorted(
        item["key"] for item in listing["items"] if item["needs_legal_review"]
    )


async def test_coverage_follows_basis_on_date(client):
    async with async_session_factory() as db:
        edition = await verified_edition(db, {"article.58": (date(2014, 1, 1), date(2019, 1, 1))})
        await link_rule(db, "art58.institution", "uk-rf", edition.id, "article.58", "ст. 58")
        await db.commit()
    plain = (await client.get(URL)).json()
    assert plain["confirmed"] == ["art58.institution"]
    assert "art58.institution" not in plain["by_status"]["no_basis"]
    in_force = (await client.get(URL, params={"on": "2018-05-01"})).json()
    assert in_force["on"] == "2018-05-01"
    assert in_force["confirmed"] == ["art58.institution"]
    expired = (await client.get(URL, params={"on": "2019-01-01"})).json()
    assert expired["confirmed"] == []
    assert expired["by_status"]["outdated"] == ["art58.institution"]
    assert expired["version"] == plain["version"] == in_force["version"]


async def test_bad_date_is_rejected(client):
    assert (await client.get(URL, params={"on": "2020-13-01"})).status_code == 422


async def test_route_does_not_shadow_rule_lookup(client):
    assert (await client.get("/api/legal/rules/art15.category")).status_code == 200
    assert (await client.get("/api/legal/rules/no.such.rule")).status_code == 404


async def test_service_matches_catalog():
    async with async_session_factory() as db:
        coverage = await rule_coverage(db)
    assert coverage["total"] == len(coverage["unconfirmed"]) + len(coverage["confirmed"])
