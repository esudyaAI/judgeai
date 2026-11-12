"""T15.12: результат анализа помнит версии санкций тех статей, которые прочитал.

T15.11 хранит отпечаток всех данных санкций, поэтому смена санкции любой другой статьи давала
`changed`. Теперь анализ записывает ещё и поштучные версии статей, санкции которых он читал
(`sanction_article_versions`: статья → отпечаток её новейшего разбора из БД, тот же, из которого
складывается `sanctions.version`). Сверка `reference-status` отдаёт блок `sanction_articles`:
`current`/`changed`/`unknown` и статус каждой статьи `current`/`changed`/`removed`. Результат,
сохранённый до T15.12, — `unknown`; блок `sanctions` (T15.11) не меняется.
"""

from sqlalchemy import select, update

from src.db.models import CriminalArticleSanction, LegalProvision, Message
from src.db.session import async_session_factory
from src.schemas.analysis import CaseAnalysis
from src.services.legal_rule_catalog import ReferenceVersions, fingerprint, reference_versions
from tests.test_analysis_reference_status import _analysed, _url
from tests.test_analysis_reference_version import GUILT, REFERENCE, _analyse
from tests.test_legal_sanction_coverage import _imported
from tests.test_statute_sanction_analysis import PART_2

A = "sha256:" + "a" * 64
B = "sha256:" + "b" * 64
SANCTIONS = "sha256:" + "5" * 64


def _reference(articles):
    return ReferenceVersions(
        catalog=REFERENCE.catalog,
        rules=REFERENCE.rules,
        sanctions=SANCTIONS,
        sanction_articles=articles,
    )


async def _add_article_159(edition_id: int) -> None:
    """A synthetic sanction of another article of the same edition (fixture data only)."""
    async with async_session_factory() as db:
        provision = await db.scalar(
            select(LegalProvision).where(
                LegalProvision.edition_id == edition_id, LegalProvision.locator == "article.159"
            )
        )
        template = await db.scalar(
            select(CriminalArticleSanction).where(CriminalArticleSanction.article == "158")
        )
        db.add(
            CriminalArticleSanction(
                provision_id=provision.id,
                article="159",
                part=1,
                ordinal=0,
                kind=template.kind,
                role=template.role,
                min_value=template.min_value,
                max_value=template.max_value,
                unit=template.unit,
                clause="наказывается ... (synthetic)",
                parser_version=template.parser_version,
            )
        )
        await db.commit()


async def _raise_article_158() -> None:
    async with async_session_factory() as db:
        await db.execute(
            update(CriminalArticleSanction)
            .where(
                CriminalArticleSanction.article == "158",
                CriminalArticleSanction.max_value.is_not(None),
            )
            .values(max_value=CriminalArticleSanction.max_value + 1)
        )
        await db.commit()


async def test_reference_versions_include_article_versions():
    async with async_session_factory() as db:
        assert (await reference_versions(db)).sanction_articles == {}
    await _imported()
    async with async_session_factory() as db:
        versions = await reference_versions(db)
    assert list(versions.sanction_articles) == ["158"]
    assert versions.sanction_articles["158"].startswith("sha256:")
    # one article's version is not the version of all sanction data
    assert versions.sanction_articles["158"] != versions.sanctions
    assert versions.sanctions != fingerprint([])


def test_analysis_stamps_versions_of_read_articles_only():
    result = _analyse(PART_2, GUILT, reference=_reference({"158": A, "159": B}))
    assert result.sanction_article_versions == {"158": A}
    assert result.sanctions_version == SANCTIONS


def test_analysis_without_reference_has_no_article_versions():
    assert _analyse(PART_2, GUILT).sanction_article_versions is None


def test_reference_without_article_versions_invents_none():
    assert _analyse(PART_2, GUILT, reference=REFERENCE).sanction_article_versions is None


def test_read_article_missing_from_versions_is_not_recorded():
    # a partial record would later read as "current" for the missing article — record nothing
    result = _analyse(PART_2, GUILT, reference=_reference({"159": B}))
    assert result.sanction_article_versions is None


def test_analysis_that_read_no_sanctions_records_empty_versions():
    result = _analyse(None, GUILT, reference=_reference({"158": A}))
    assert result.sanction_article_versions == {}


def test_results_stored_before_article_versions_still_load():
    stored = _analyse(PART_2, GUILT, reference=_reference({"158": A})).model_dump(mode="json")
    stored.pop("sanction_article_versions")
    assert CaseAnalysis.model_validate(stored).sanction_article_versions is None


async def test_change_of_another_article_keeps_read_articles_current(client):
    edition_id = await _imported()
    chat_id, message, result = await _analysed(client)
    async with async_session_factory() as db:
        current = (await reference_versions(db)).sanction_articles
    assert result["sanction_article_versions"] == {"158": current["158"]}
    fresh = (await client.get(_url(chat_id, message))).json()["sanction_articles"]
    assert fresh == {
        "status": "current",
        "changed_articles": [],
        "articles": [
            {
                "article": "158",
                "stored_version": current["158"],
                "current_version": current["158"],
                "status": "current",
            }
        ],
    }

    await _add_article_159(edition_id)
    status = (await client.get(_url(chat_id, message))).json()
    assert status["sanctions"]["status"] == "changed"  # T15.11: all sanction data
    assert status["sanction_articles"]["status"] == "current"  # T15.12: what was read

    await _raise_article_158()
    status = (await client.get(_url(chat_id, message))).json()
    articles = status["sanction_articles"]
    assert articles["status"] == "changed"
    assert articles["changed_articles"] == ["158"]
    assert articles["articles"][0]["status"] == "changed"
    assert articles["articles"][0]["stored_version"] == result["sanction_article_versions"]["158"]
    assert status["status"] == "current"  # the rule catalog is unchanged


async def test_result_without_article_versions_is_unknown(client):
    await _imported()
    chat_id, message, _ = await _analysed(client)
    async with async_session_factory() as db:
        stored = await db.get(Message, message)
        analysis = dict(stored.analysis)
        analysis.pop("sanction_article_versions")
        await db.execute(update(Message).where(Message.id == message).values(analysis=analysis))
        await db.commit()
    articles = (await client.get(_url(chat_id, message))).json()["sanction_articles"]
    assert articles == {"status": "unknown", "changed_articles": [], "articles": []}
