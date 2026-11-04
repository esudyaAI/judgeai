import io
from uuid import uuid4
from zipfile import ZipFile

import pytest

from tests.test_fact_review import proof
from tests.test_review_sources import analysed
from tests_unit.test_fine_credit_review import CREDIT


def command(base, value):
    return {
        "base_revision_id": base,
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/sentence/fine_credit/new",
                "operation": "correct",
                "reason": "Сверено решение о штрафе",
                "value": value,
                "evidence": proof(),
            }
        ],
    }


async def test_credit_correction_unknown_and_docx_preserve_original_imposed_term(client):
    path, base = await analysed(client)
    body = command(base, {**CREDIT, "scope": "count", "count_index": 0})
    response = await client.post(path + "/review", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    sentence = result["defendants"][1]["imposed_sentence"]
    assert sentence["counts"][0]["imprisonment_months"] == 48
    assert sentence["fine_credits"][0]["released"] is False
    assert sentence["fine_credits"][0]["reduced_amount"] == 5000
    check = next(c for c in result["defendants"][1]["legal_checks"] if "72 УК РФ" in c["norm"])
    assert check["status"] == "insufficient_data"
    report = await client.post(path + "/reports")
    assert report.status_code == 201, report.text
    artifact = (await client.get(f"/api/reports/{report.json()['id']}/docx")).content
    with ZipFile(io.BytesIO(artifact)) as doc:
        xml = doc.read("word/document.xml").decode()
    assert "Сверено решение о штрафе" in xml and "Назначенный штраф" in xml
    assert "reduced_amount" not in xml
    unknown = {
        "base_revision_id": result["revision"]["id"],
        "client_request_id": str(uuid4()),
        "decisions": [
            {
                "fact_id": "subject/1/sentence/fine_credit/0",
                "operation": "unknown",
                "reason": "Противоречивое решение о зачёте",
            }
        ],
    }
    response = await client.post(path + "/review", json=unknown)
    assert response.status_code == 200, response.text
    result = response.json()
    unknown_check = next(
        c for c in result["defendants"][1]["legal_checks"] if "72 УК РФ" in c["norm"]
    )
    assert "неизвестным пользователем" in unknown_check["explanation"]
    assert unknown_check["evidence"] == []
    credit = result["defendants"][1]["imposed_sentence"]["fine_credits"][0]
    assert credit["unknown"] is True and credit["released"] is None
    assert credit["original_amount"] is None and credit["reduced_amount"] is None
    detail = (await client.get(path + "/revisions/" + result["revision"]["id"])).json()
    stored = detail["calculation_inputs"]["kwargs"]["prepared_sentencing_inputs"]["1"]
    assert len(stored["sentence"]["fine_credits"]) == 1
    assert stored["sentence"]["fine_credits"][0]["reduced_amount"] == 5000
    assert "fine_credit/0" in stored["unknown_fields"]
    report = (await client.post(path + "/reports")).json()
    artifact = (await client.get(f"/api/reports/{report['id']}/docx")).content
    with ZipFile(io.BytesIO(artifact)) as doc:
        assert (
            "Сведения о зачёте штрафа не установлены пользователем."
            in doc.read("word/document.xml").decode()
        )


@pytest.mark.parametrize(
    "change",
    [
        {"reduced_amount": True},
        {"scope": "count", "count_index": 99},
        {"scope": "count", "count_index": True},
        {"released": True},
        {"status": "verified"},
        {"days": 30},
    ],
)
async def test_invalid_fine_credit_does_not_write_a_version(client, change):
    path, base = await analysed(client)
    response = await client.post(path + "/review", json=command(base, {**CREDIT, **change}))
    assert response.status_code == 422, response.text
    assert len((await client.get(path + "/revisions")).json()) == 1
