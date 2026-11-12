"""T15.15: две редакции с одной датой получения — отказ, а не порядок строк БД.

Новейший разбор санкций статьи выбирался `ORDER BY retrieved_at DESC`: при равенстве дат
поиск санкций (`find_article_sanctions`) и версии справки (T15.10–T15.12) молча брали ту
редакцию, которую БД вернула первой. Теперь конфликт закрывается отказом (DoD T23).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.db.models import CriminalArticleSanction, LegalProvision
from src.db.session import async_session_factory
from src.services.criminal_sanction_import import import_criminal_sanctions
from src.services.criminal_sanction_lookup import find_article_sanctions
from src.services.legal_library import import_snapshot
from src.services.legal_rule_catalog import reference_versions, sanction_coverage
from tests.test_criminal_sanctions import _manifest, _seed
from tests.test_sanction_lookup_reading import NEWER_RAW, _newer_manifest

SEED_MOMENT = _manifest().retrieved_at


async def _second_edition(retrieved_at: datetime) -> tuple[int, int]:
    """The seeded edition of art. 158 and a synthetic second one retrieved at `retrieved_at`."""
    first_id = await _seed()
    manifest = _newer_manifest().model_copy(update={"retrieved_at": retrieved_at})
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, first_id)
        second, _ = await import_snapshot(db, manifest, NEWER_RAW)
        await db.commit()
        second_id = second.id
        await import_criminal_sanctions(db, second_id)
    return first_id, second_id


async def test_lookup_refuses_two_editions_retrieved_at_the_same_moment():
    await _second_edition(SEED_MOMENT)
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="same moment"):
            await find_article_sanctions(db, "158")
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="same moment"):
            await find_article_sanctions(db, "158", 1)


async def test_reference_versions_and_coverage_refuse_the_tie():
    await _second_edition(SEED_MOMENT)
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="same moment"):
            await reference_versions(db)
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="same moment"):
            await sanction_coverage(db)


async def test_distinct_moments_keep_choosing_the_later_edition():
    _, second_id = await _second_edition(datetime(2026, 11, 1, tzinfo=UTC))
    async with async_session_factory() as db:
        whole = await find_article_sanctions(db, "158")
        versions = await reference_versions(db)
    assert whole.provenance.edition_id == second_id
    assert "158" in versions.sanction_articles


async def test_tie_of_another_article_does_not_block_this_one():
    """The tie is per article: art. 158 has two editions at one moment, art. 159 only one."""
    first_id, _ = await _second_edition(SEED_MOMENT)
    async with async_session_factory() as db:
        rows = (
            await db.scalars(
                select(CriminalArticleSanction)
                .join(LegalProvision, LegalProvision.id == CriminalArticleSanction.provision_id)
                .where(
                    CriminalArticleSanction.article == "158",
                    LegalProvision.edition_id == first_id,
                )
            )
        ).all()
        provision_159 = await db.scalar(
            select(LegalProvision.id).where(
                LegalProvision.edition_id == first_id, LegalProvision.locator == "article.159"
            )
        )
        for row in rows:  # synthetic fixture: art. 159 sanctions in the first edition only
            db.add(
                CriminalArticleSanction(
                    provision_id=provision_159,
                    article="159",
                    part=row.part,
                    ordinal=row.ordinal,
                    kind=row.kind,
                    role=row.role,
                    min_value=row.min_value,
                    max_value=row.max_value,
                    unit=row.unit,
                    clause=row.clause,
                    parser_version=row.parser_version,
                )
            )
        await db.commit()
    async with async_session_factory() as db:
        other = await find_article_sanctions(db, "159")
    assert other.provenance.edition_id == first_id
    assert len(other.sanctions) == len(rows)
