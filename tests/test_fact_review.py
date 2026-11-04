from copy import deepcopy
from uuid import UUID, uuid4

import pytest

from src.db.models import Message
from src.db.session import async_session_factory
from src.domain.extraction import input_hash
from tests.test_auth import account, anonymous, login
from tests.test_multidefendant_analysis import TEXT
from tests.test_review_sources import analysed


def proof():
    quote = "ФИО2 признать виновным по ч. 2 ст. 161 УК РФ"
    start = TEXT.index(quote)
    return {
        "document_index": 0,
        "document_hash": input_hash(TEXT),
        "start": start,
        "end": start + len(quote),
        "quote": quote,
    }


def command(base, field="subject/1/legal/stated_recidivism", value="none"):
    return {
        "base_revision_id": base,
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": field,
                "operation": "correct",
                "value": value,
                "reason": "Синтетическая проверка",
                "evidence": proof(),
            }
        ],
    }


def recidivism(result, subject=1):
    return next(
        check
        for check in result["defendants"][subject]["legal_checks"]
        if check["norm"] == "ст. 18 УК РФ"
    )


async def test_human_decisions_change_rule_inputs_and_preserve_immutable_history(
    client, monkeypatch
):
    path, base = await analysed(client)
    old = (await client.get(path + f"/revisions/{base}")).json()
    old_report = (await client.post(path + "/reports")).json()
    report_url = f"/api/reports/{old_report['id']}/docx"
    artifact = (await client.get(report_url)).content
    body = command(base)
    for field, value in (
        ("guilt", "intentional"),
        ("category", "grave"),
        ("real_imprisonment", True),
        ("history_complete", True),
    ):
        body["decisions"].append(
            {
                "fact_id": f"subject/1/legal/{field}",
                "operation": "correct",
                "value": value,
                "reason": "Сверено с источником",
                "evidence": proof(),
            }
        )

    async def forbidden(*args, **kwargs):
        raise AssertionError("human replay must not call LLM")

    monkeypatch.setattr("src.services.case_analyzer.extract_facts", forbidden)
    saved = await client.post(path + "/review", json=body)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result["revision"]["version"] == 2 and result["revision"]["kind"] == "human"
    assert result["revision"]["base_revision_id"] == base
    assert recidivism(result)["status"] == "ok" and recidivism(result)["value"] == "none"
    assert result["defendants"][0] == old["result"]["defendants"][0]
    assert result["human_review"]["status"] == "partially_reviewed"
    assert result["human_review"]["legal_approval"] is False
    assert len(result["human_review"]["decisions"]) == 5
    practice = await client.get(path.rsplit("/messages/", 1)[0] + "/precedents?defendant=2")
    assert practice.status_code == 200 and practice.json()["query"] is None
    assert "После исправления" in practice.json()["note"]
    assert result["human_review"]["decisions"][0]["actor_id"] > 0
    assert (await client.get(path)).json()["result"] == result
    assert (await client.get(path + f"/revisions/{base}")).json() == old
    assert (await client.get(report_url)).content == artifact
    current = (await client.get(path + f"/revisions/{result['revision']['id']}")).json()
    assert current["calculation_inputs"]["review_invalidations"] == []
    assert (
        current["calculation_inputs"]["review_practice_refresh"]["subjects"]["1"]["status"]
        == "unavailable"
    )
    assert result["human_review"]["practice_invalidated"] is True
    facts = (await client.get(path + f"/revisions/{result['revision']['id']}/facts")).json()
    assert (
        next(item for item in facts if item["id"] == "subject/1/legal/guilt")["value"]
        == "intentional"
    )
    unknown = {
        "base_revision_id": result["revision"]["id"],
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/legal/history_complete",
                "operation": "unknown",
                "reason": "История не установлена",
            }
        ],
    }
    revised = await client.post(path + "/review", json=unknown)
    assert revised.status_code == 200, revised.text
    assert recidivism(revised.json())["status"] == "insufficient_data"
    assert len(revised.json()["human_review"]["decisions"]) == 6
    assert len((await client.get(path + "/revisions")).json()) == 3
    # The new current report has a readable partial-review label; old bytes remain fixed.
    report = await client.post(path + "/reports")
    assert report.status_code == 201, report.text
    import io
    from zipfile import ZipFile

    with ZipFile(
        io.BytesIO((await client.get(f"/api/reports/{report.json()['id']}/docx")).content)
    ) as doc:
        xml = doc.read("word/document.xml").decode()
    assert "Часть фактов проверена пользователем" in xml and "partially_reviewed" not in xml
    assert "История не установлена" in xml and "Синтетическая проверка" in xml
    assert "Указанный в приговоре рецидив" in xml and input_hash(TEXT) in xml
    assert "новое значение: умышленная" in xml
    assert "значение: intentional" not in xml


async def test_idempotency_replay_stale_base_and_key_conflicts(client):
    path, base = await analysed(client)
    body = command(base)
    first = await client.post(path + "/review", json=body)
    assert first.status_code == 200, first.text
    assert (await client.post(path + "/review", json=body)).json() == first.json()
    reused = deepcopy(body)
    reused["decisions"][0]["value"] = "simple"
    assert (await client.post(path + "/review", json=reused)).status_code == 409
    assert (await client.post(path + "/review", json=command(base))).status_code == 409
    chat_id = int(path.split("/")[3])
    async with async_session_factory() as db:
        db.add(Message(chat_id=chat_id, role="assistant", status="running"))
        await db.commit()
    # Lost-response retries return the stored version even while the case is now busy.
    assert (await client.post(path + "/review", json=body)).json() == first.json()
    fresh = command(first.json()["revision"]["id"])
    assert (await client.post(path + "/review", json=fresh)).status_code == 409
    assert len((await client.get(path + "/revisions")).json()) == 2


async def test_foreign_anonymous_csrf_and_wrong_source_rejected(client):
    path, base = await analysed(client)
    body = command(base)
    csrf = client.headers.pop("X-CSRF-Token")
    assert (await client.post(path + "/review", json=body)).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    await account("review-stranger")
    async with anonymous() as stranger:
        assert (await stranger.post(path + "/review", json=body)).status_code == 401
        await login(stranger, "review-stranger")
        assert (await stranger.post(path + "/review", json=body)).status_code == 404
        assert (await stranger.get(path + f"/revisions/{base}/facts")).status_code == 404
    body["decisions"][0]["fact_id"] = "subject/0/legal/stated_recidivism"
    assert (await client.post(path + "/review", json=body)).status_code == 422
    assert len((await client.get(path + "/revisions")).json()) == 1


@pytest.mark.parametrize(
    "change",
    [
        "integer_boolean",
        "unknown_field",
        "duplicate_field",
        "missing_reason",
        "bad_quote",
        "extra_actor",
        "unknown_confirm",
    ],
)
async def test_invalid_commands_leave_no_revision(client, change):
    path, base = await analysed(client)
    body = command(base)
    item = body["decisions"][0]
    if change == "integer_boolean":
        item.update(fact_id="subject/1/regime/male", value=1)
    elif change == "unknown_field":
        item["fact_id"] = "subject/1/legal/__dict__"
    elif change == "duplicate_field":
        body["decisions"].append(deepcopy(item))
    elif change == "missing_reason":
        item["reason"] = " "
    elif change == "bad_quote":
        item["evidence"]["quote"] = "PRIVATE-SYNTHETIC-INCORRECT"
    elif change == "extra_actor":
        item["actor_id"] = 999
    else:
        item.update(fact_id="subject/1/legal/history_complete", operation="confirm", value=None)
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 422, response.text
    assert "PRIVATE-SYNTHETIC-INCORRECT" not in response.text
    assert len((await client.get(path + "/revisions")).json()) == 1


async def test_failure_after_insert_rolls_back_current_result_and_idempotency(
    client, monkeypatch, caplog
):
    from src.infrastructure.analysis_revisions import SqlAnalysisRevisionStore

    path, base = await analysed(client)
    before = (await client.get(path)).json()["result"]
    append = SqlAnalysisRevisionStore.append

    async def fail_after_flush(self, *args, **kwargs):
        await append(self, *args, **kwargs)
        raise RuntimeError("SYNTHETIC-PRIVATE-DETAIL")

    monkeypatch.setattr(SqlAnalysisRevisionStore, "append", fail_after_flush)
    body = command(base)
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 503, response.text
    assert "SYNTHETIC-PRIVATE-DETAIL" not in response.text + caplog.text
    assert (await client.get(path)).json()["result"] == before
    assert len((await client.get(path + "/revisions")).json()) == 1
    monkeypatch.setattr(SqlAnalysisRevisionStore, "append", append)
    retried = await client.post(path + "/review", json=body)
    assert retried.status_code == 200 and retried.json()["revision"]["version"] == 2


async def test_concurrent_duplicate_delivery_creates_exactly_one_revision(client):
    import asyncio

    path, base = await analysed(client)
    body = command(base)
    responses = await asyncio.gather(*(client.post(path + "/review", json=body) for _ in range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert len((await client.get(path + "/revisions")).json()) == 2


async def test_unsupported_engine_and_tampered_review_are_not_editable(client):
    from src.db.analysis_revisions import AnalysisRevision
    from src.domain.reports import freeze_snapshot

    path, base = await analysed(client)
    async with async_session_factory() as db:
        row = await db.get(AnalysisRevision, UUID(base))
        payload = deepcopy(row.calculation_inputs)
        payload["engine_version"] = "future-engine"
        row.calculation_inputs, row.inputs_sha256 = freeze_snapshot(payload)
        await db.commit()
    assert (await client.post(path + "/review", json=command(base))).status_code == 409
    async with async_session_factory() as db:
        row = await db.get(AnalysisRevision, UUID(base))
        row.review = {"status": "partially_reviewed", "actor_id": 999}
        await db.commit()
    assert (await client.get(path + f"/revisions/{base}")).status_code == 409


async def test_malformed_command_does_not_echo_private_body(client):
    path, _ = await analysed(client)
    response = await client.post(
        path + "/review", json={"decisions": [{"reason": "PRIVATE-SYNTHETIC-CONTENT"}]}
    )
    assert response.status_code == 422
    assert "PRIVATE-SYNTHETIC-CONTENT" not in response.text
