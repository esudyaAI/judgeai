"""T15.13: a part's sanctions come only from the newest reading of the whole article.

The per-article version (T15.12) fingerprints the newest reading of the article. Asked for one
part, the lookup used to pick the newest reading among the rows of that part, so a part absent
from the newest reading was silently read from an older edition (or an older parser) while the
result recorded the newest version. Such a part is now "not parsed" — never an older edition.
"""

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import update

from src.db.models import CriminalArticleSanction
from src.db.session import async_session_factory
from src.schemas.legal_library import SnapshotImport
from src.services.criminal_sanction_import import import_criminal_sanctions
from src.services.criminal_sanction_lookup import find_article_sanctions
from src.services.legal_library import import_snapshot
from tests.test_criminal_sanctions import _manifest, _seed

PART_1_ONLY = (
    "Статья 158. Кража1. Кража -наказывается штрафом в размере до восьмидесяти тысяч рублей, "
    "либо лишением свободы на срок до трех лет."
)
NEWER_RAW = b"synthetic newer edition with only part 1 of article 158"
NEWER_PARSER = "zz-test-newer-parser"


def _newer_manifest() -> SnapshotImport:
    data = _manifest().model_dump()
    data.update(
        raw_sha256=sha256(NEWER_RAW).hexdigest(),
        retrieved_at=datetime(2026, 11, 1, tzinfo=UTC),
        edition_label="Synthetic newer edition",
        full_text=PART_1_ONLY,
        provisions=[
            {
                "locator": "article.158",
                "title": "Статья 158. Кража",
                "body": PART_1_ONLY,
                "ordinal": 0,
            }
        ],
    )
    return SnapshotImport.model_validate(data)


async def _two_editions() -> tuple[int, int]:
    """An older edition with parts 1–2 of art. 158 and a newer one that has only part 1."""
    older_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, older_id)
        newer, _ = await import_snapshot(db, _newer_manifest(), NEWER_RAW)
        await db.commit()
        newer_id = newer.id
        await import_criminal_sanctions(db, newer_id)
    return older_id, newer_id


async def test_part_missing_from_newest_edition_is_not_read_from_older_edition():
    _, newer_id = await _two_editions()
    async with async_session_factory() as db:
        part_1 = await find_article_sanctions(db, "158", 1)
        part_2 = await find_article_sanctions(db, "158", 2)
        whole = await find_article_sanctions(db, "158")
    assert part_1.provenance.edition_id == newer_id
    assert {(s.kind.value, s.max_value) for s in part_1.sanctions} == {
        ("fine", 80_000),
        ("imprisonment", 36),
    }
    assert part_2 is None
    assert whole.provenance.edition_id == newer_id
    assert {s.part for s in whole.sanctions} == {1}


async def test_api_does_not_serve_a_part_from_an_older_edition(client):
    await _two_editions()
    response = await client.get("/api/legal/sanctions", params={"article": "158", "part": 2})
    assert response.status_code == 404


async def test_part_missing_from_newest_parser_reading_is_not_read_from_older_parser():
    edition_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, edition_id)
        await db.execute(
            update(CriminalArticleSanction)
            .where(CriminalArticleSanction.article == "158", CriminalArticleSanction.part == 1)
            .values(parser_version=NEWER_PARSER)
        )
        await db.commit()
        part_1 = await find_article_sanctions(db, "158", 1)
        part_2 = await find_article_sanctions(db, "158", 2)
    assert part_1.provenance.parser_version == NEWER_PARSER
    assert part_2 is None


async def test_single_edition_lookup_is_unchanged():
    edition_id = await _seed()
    async with async_session_factory() as db:
        await import_criminal_sanctions(db, edition_id)
        part_2 = await find_article_sanctions(db, "158", 2)
        whole = await find_article_sanctions(db, "158")
    assert part_2.provenance.edition_id == edition_id
    assert [(s.kind.value, s.role.value, s.max_value) for s in part_2.sanctions] == [
        ("imprisonment", "main", 60),
        ("restriction_of_freedom", "additional", 12),
    ]
    assert {s.part for s in whole.sanctions} == {1, 2}
