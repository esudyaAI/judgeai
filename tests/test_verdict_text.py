"""A similar verdict opens as plain text in the document panel; private documents stay closed."""

from src.db.models import KnowledgeVerdict
from src.db.session import async_session_factory
from tests.fixtures.synthetic_verdicts import PRACTICE_THEFT
from tests.test_auth import account, anonymous, login


async def _verdict(source_type="manual", raw_text=PRACTICE_THEFT, case_number="1-23/2024"):
    async with async_session_factory() as db:
        verdict = KnowledgeVerdict(
            raw_text=raw_text, source_type=source_type, case_number=case_number
        )
        db.add(verdict)
        await db.commit()
        return verdict.id


async def _signed_in(client):
    await account("alice")
    await login(client, "alice")


async def test_public_verdict_text_is_served_inline_and_as_download():
    verdict_id = await _verdict()
    async with anonymous() as client:
        await _signed_in(client)
        r = await client.get(f"/api/knowledge/verdicts/{verdict_id}/text")
        assert r.status_code == 200
        assert r.text == PRACTICE_THEFT
        assert r.headers["content-type"].startswith("text/plain")
        assert "utf-8" in r.headers["content-type"].lower()
        assert r.headers["content-disposition"].startswith("inline")
        assert "sandbox" in r.headers["content-security-policy"]
        assert r.headers["x-content-type-options"] == "nosniff"
        download = await client.get(f"/api/knowledge/verdicts/{verdict_id}/text?download=true")
        assert download.headers["content-disposition"].startswith("attachment")
        assert f"verdict-{verdict_id}.txt" in download.headers["content-disposition"]


async def test_private_missing_or_empty_verdict_text_is_not_found():
    private_id = await _verdict(source_type="chat", raw_text="Протокол допроса Смирнова")
    empty_id = await _verdict(raw_text="   ")
    async with anonymous() as client:
        await _signed_in(client)
        for verdict_id in (private_id, empty_id, 999_999):
            r = await client.get(f"/api/knowledge/verdicts/{verdict_id}/text")
            assert r.status_code == 404
            assert "Смирнова" not in r.text


async def test_verdict_text_requires_sign_in():
    verdict_id = await _verdict()
    async with anonymous() as client:
        r = await client.get(f"/api/knowledge/verdicts/{verdict_id}/text")
        assert r.status_code == 401
        assert "похитил" not in r.text
