"""Uploading a verdict to the knowledge base builds its precedent card at once (regex);
fabula vectors are computed afterwards and their failure never fails the upload."""

from sqlalchemy import func, select

from src.db.models import KnowledgeVerdict
from src.db.precedents import PrecedentCardRow, PrecedentEmbedding
from src.db.session import async_session_factory
from tests.fixtures.fake_embedder import HashingEmbedder
from tests.fixtures.synthetic_verdicts import NO_HEADINGS, PRACTICE_ROBBERY, PRACTICE_THEFT

THEFT = "п. «в» ч. 2 ст. 158 УК РФ"


async def _count(model):
    async with async_session_factory() as db:
        return await db.scalar(select(func.count()).select_from(model))


def _files(*texts):
    return [("files", (f"v{i}.txt", t.encode(), "text/plain")) for i, t in enumerate(texts)]


async def _upload(client, *texts, source_type="manual"):
    r = await client.post(
        "/api/knowledge/verdicts/upload", files=_files(*texts), data={"source_type": source_type}
    )
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _with_embedder(embedder):
    from src.api.precedents import get_embedder
    from src.main import app

    app.dependency_overrides[get_embedder] = lambda: embedder
    return lambda: app.dependency_overrides.pop(get_embedder, None)


async def test_upload_builds_card_and_reports_what_was_read(client):
    restore = _with_embedder(HashingEmbedder())
    try:
        theft, robbery = await _upload(client, PRACTICE_THEFT, PRACTICE_ROBBERY)
    finally:
        restore()
    assert theft["precedent"]["qualifications"] == [THEFT]
    assert theft["precedent"]["punishment_months"] == 18
    assert theft["precedent"]["conditional"] is True
    assert robbery["precedent"]["qualifications"] == ["ч. 1 ст. 161 УК РФ"]
    assert robbery["precedent"]["recidivism"] == "dangerous"
    assert await _count(PrecedentCardRow) == 2
    assert await _count(PrecedentEmbedding) == 2  # vectors computed after the response


async def test_reupload_reuses_the_existing_card(client):
    first = (await _upload(client, PRACTICE_THEFT))[0]
    second = (await _upload(client, PRACTICE_THEFT))[0]
    assert second["duplicate"] is True
    assert second["precedent"]["card_id"] == first["precedent"]["card_id"]
    assert await _count(PrecedentCardRow) == 1


async def test_private_source_type_cannot_be_uploaded(client):
    """Private documents come only from a user's own case, never through the shared upload."""
    r = await client.post(
        "/api/knowledge/verdicts/upload", files=_files(PRACTICE_THEFT), data={"source_type": "chat"}
    )
    assert r.status_code == 422 and "источник" in r.json()["detail"].lower()
    assert await _count(KnowledgeVerdict) == 0 and await _count(PrecedentCardRow) == 0


async def test_unrecognised_text_is_kept_with_an_empty_card(client):
    item = (await _upload(client, NO_HEADINGS))[0]
    assert item["precedent"]["qualifications"] == []
    assert item["precedent"]["punishment_months"] is None


async def test_embedding_failure_does_not_fail_the_upload(client):
    # conftest disables the real embedder: the card is saved, no vector is written.
    item = (await _upload(client, PRACTICE_THEFT))[0]
    assert item["precedent"]["qualifications"] == [THEFT]
    assert await _count(PrecedentEmbedding) == 0
