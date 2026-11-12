"""T15.14: новейший разбор статьи выбирается по номеру версии парсера, а не по тексту.

`parser_version.desc()` сортировал версии как строки: «statute-sanction-parser/2» выше
«…/10». После выпуска десятой версии парсера анализ, справка и версии санкций продолжали бы
опираться на старый разбор. Теперь порядок — `src.domain.parser_versions`.
"""

import pytest
from sqlalchemy import delete, select

from src.db.models import CriminalArticleSanction
from src.db.session import async_session_factory
from src.services.criminal_sanction_lookup import find_article_sanctions
from src.services.legal_rule_catalog import reference_versions
from src.services.statute_sanction_parser import PARSER_VERSION
from tests.test_legal_sanction_coverage import _imported

SCHEME = PARSER_VERSION.split("/")[0]
CURRENT = PARSER_VERSION
TENTH = f"{SCHEME}/10"


async def _add_reading(version: str) -> None:
    """A synthetic re-reading of art. 158 by another parser version, max + 1 (fixture data)."""
    async with async_session_factory() as db:
        rows = (
            await db.scalars(
                select(CriminalArticleSanction).where(
                    CriminalArticleSanction.article == "158",
                    CriminalArticleSanction.parser_version == CURRENT,
                )
            )
        ).all()
        for row in rows:
            db.add(
                CriminalArticleSanction(
                    provision_id=row.provision_id,
                    article=row.article,
                    part=row.part,
                    ordinal=row.ordinal,
                    kind=row.kind,
                    role=row.role,
                    min_value=row.min_value,
                    max_value=None if row.max_value is None else row.max_value + 1,
                    unit=row.unit,
                    clause=row.clause,
                    parser_version=version,
                )
            )
        await db.commit()


async def _drop(version: str) -> None:
    async with async_session_factory() as db:
        await db.execute(
            delete(CriminalArticleSanction).where(CriminalArticleSanction.parser_version == version)
        )
        await db.commit()


async def test_lookup_prefers_tenth_parser_version_over_second():
    await _imported()
    async with async_session_factory() as db:
        before = await find_article_sanctions(db, "158", 2)
    await _add_reading(TENTH)
    async with async_session_factory() as db:
        after = await find_article_sanctions(db, "158", 2)
    assert after.provenance.parser_version == TENTH
    assert [s.max_value for s in after.sanctions] == [
        None if s.max_value is None else s.max_value + 1 for s in before.sanctions
    ]


async def test_article_version_rests_on_the_numerically_newest_reading():
    await _imported()
    await _add_reading(TENTH)
    async with async_session_factory() as db:
        both = await reference_versions(db)
    await _drop(CURRENT)
    async with async_session_factory() as db:
        tenth_only = await reference_versions(db)
    assert both.sanction_articles["158"] == tenth_only.sanction_articles["158"]
    assert both.sanctions == tenth_only.sanctions


async def test_unordered_parser_versions_are_refused_not_guessed():
    await _imported()
    await _add_reading("zz-unnumbered-parser")
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="parser version"):
            await find_article_sanctions(db, "158")
    async with async_session_factory() as db:
        with pytest.raises(ValueError, match="parser version"):
            await reference_versions(db)
