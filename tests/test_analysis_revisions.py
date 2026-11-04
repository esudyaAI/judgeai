import pytest

from src.infrastructure.calculation_inputs import replay_inputs
from tests.test_auth import account, anonymous, login
from tests.test_reports import analysed


async def test_machine_revision_contains_replayable_inputs_and_is_owner_scoped(client):
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/revisions"
    history = await client.get(path)
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    revision = history.json()[0]
    assert revision["version"] == 1 and revision["kind"] == "machine"
    detail = (await client.get(path + "/" + revision["id"])).json()
    assert "stored_path" not in str(detail)
    replayed = replay_inputs(detail["calculation_inputs"]).model_dump(mode="json")
    expected = {**detail["result"], "revision": None, "human_review": None}
    assert replayed == expected
    assert "no-store" in history.headers["cache-control"]
    await account("revision-stranger")
    async with anonymous() as stranger:
        await login(stranger, "revision-stranger")
        assert (await stranger.get("/api/account/export")).json()["analysis_revisions"] == []
        assert (await stranger.get(path)).status_code == 404
        assert (await stranger.get(path + "/" + revision["id"])).status_code == 404


async def test_recalculate_preserves_previous_revision_and_report(client):
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}"
    first = (await client.get(path + "/revisions")).json()[0]
    before = (await client.get(path + "/revisions/" + first["id"])).json()
    report = (await client.post(path + "/reports")).json()
    artifact = (await client.get(f"/api/reports/{report['id']}/docx")).content
    assert (await client.post(path + "/recalculate")).status_code == 202
    history = (await client.get(path + "/revisions")).json()
    assert [row["version"] for row in history] == [2, 1]
    assert (await client.get(path + "/revisions/" + first["id"])).json() == before
    assert (await client.get(f"/api/reports/{report['id']}/docx")).content == artifact


async def test_failed_recalculation_archives_legacy_without_inventing_inputs(client, monkeypatch):
    from src.db.models import Message
    from src.db.session import async_session_factory
    from src.services import analysis_runner
    from src.services.llm_client import LLMError

    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}"
    async with async_session_factory() as db:
        row = await db.get(Message, message)
        row.analysis = {
            **row.analysis,
            "fabula": "Legacy unarchived result",
            "revision": None,
            "human_review": None,
        }
        await db.commit()

    class Failed:
        async def complete_json(self, *args):
            raise LLMError("synthetic failure")

    monkeypatch.setattr(analysis_runner, "get_llm_client", lambda: Failed())
    assert (await client.post(path + "/recalculate")).status_code == 202
    assert (await client.get(path)).json()["status"] == "failed"
    history = (await client.get(path + "/revisions")).json()
    assert [row["kind"] for row in history] == ["legacy", "machine"]
    legacy = (await client.get(path + "/revisions/" + history[0]["id"])).json()
    assert legacy["calculation_inputs"] is None and legacy["inputs_sha256"] is None
    assert legacy["result"]["fabula"] == "Legacy unarchived result"
    assert legacy["review"]["status"] == "unknown"


async def test_revision_export_cascade_and_wrong_source_are_scoped(client):
    chat, message = await analysed(client)
    other_chat, other_message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/revisions"
    first = (await client.get(path)).json()[0]
    wrong = f"/api/chats/{other_chat}/messages/{other_message}/revisions/{first['id']}"
    assert (await client.get(wrong)).status_code == 404
    assert (
        await client.post(f"/api/chats/{chat}/messages/{message}/recalculate")
    ).status_code == 202
    exported = (await client.get("/api/account/export")).json()["analysis_revisions"]
    assert {item["source_message_id"] for item in exported} == {message, other_message}
    assert "stored_path" not in str(exported)
    assert (await client.delete(f"/api/chats/{chat}")).status_code == 200
    assert (await client.get(path)).status_code == 404
    remaining = (
        await client.get(f"/api/chats/{other_chat}/messages/{other_message}/revisions")
    ).json()
    assert len(remaining) == 1


@pytest.mark.parametrize("tamper", ["erase_inputs", "alter_result"])
async def test_revision_integrity_detects_tampered_inputs(client, tamper):
    from uuid import UUID

    from src.db.analysis_revisions import AnalysisRevision
    from src.db.session import async_session_factory

    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}/revisions"
    revision = (await client.get(path)).json()[0]
    async with async_session_factory() as db:
        row = await db.get(AnalysisRevision, UUID(revision["id"]))
        if tamper == "erase_inputs":
            row.calculation_inputs = None
        else:
            row.result = {**row.result, "fabula": "Changed later"}
        await db.commit()
    assert (await client.get(path + "/" + revision["id"])).status_code == 409


async def test_failed_revision_save_rolls_back_both_history_and_current_result(
    client, monkeypatch, caplog
):
    from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore

    append = SqlAnalysisRevisionStore.append

    async def fail_after_flush(self, *args, **kwargs):
        await append(self, *args, **kwargs)
        raise RuntimeError("SYNTHETIC-PRIVATE-DETAIL")

    monkeypatch.setattr(SqlAnalysisRevisionStore, "append", fail_after_flush)
    chat, message = await analysed(client)
    path = f"/api/chats/{chat}/messages/{message}"
    failed = (await client.get(path)).json()
    assert failed["status"] == "failed" and failed["result"] is None
    assert (await client.get(path + "/revisions")).json() == []
    assert "SYNTHETIC-PRIVATE-DETAIL" not in caplog.text
    monkeypatch.setattr(SqlAnalysisRevisionStore, "append", append)
    assert (await client.post(path + "/recalculate")).status_code == 202
    history = (await client.get(path + "/revisions")).json()
    assert len(history) == 1 and history[0]["version"] == 1
