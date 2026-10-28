"""Real routes preserve reading failures and do not analyze/index missing input."""

import pytest

from src.config import settings
from tests.test_docx_uploads import upload_url
from tests_pdf.fixtures import image_pdf
from tests_uploads.test_docx_guard import CONTENT_TYPES, archive


@pytest.mark.parametrize("raw", [b"", b"   ", b"ab\x00cd", b"hello\xc3"])
async def test_unreadable_text_never_becomes_a_knowledge_verdict(
    client, monkeypatch, tmp_path, raw
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    response = await client.post(
        "/api/knowledge/verdicts/upload", files=[("files", ("synthetic.txt", raw, "text/plain"))]
    )
    assert response.status_code == 422
    assert (await client.get("/api/knowledge/verdicts")).json()["total"] == 0
    assert list(tmp_path.iterdir()) == []


async def test_image_only_pdf_is_not_indexed_as_empty_knowledge(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    response = await client.post(
        "/api/knowledge/verdicts/upload",
        files=[("files", ("scan.pdf", image_pdf(), "application/pdf"))],
    )
    assert response.status_code == 422
    assert "OCR" in response.text
    assert (await client.get("/api/knowledge/verdicts")).json()["total"] == 0
    assert list(tmp_path.iterdir()) == []


async def test_no_text_and_no_question_fails_before_llm(client, monkeypatch):
    def unexpected_llm():
        pytest.fail("LLM must not be requested without usable input")

    monkeypatch.setattr("src.services.analysis_runner.get_llm_client", unexpected_llm)
    url = await upload_url(client, "chat")
    response = await client.post(url, files=[("files", ("empty.txt", b" ", "text/plain"))])
    assert response.status_code == 202
    messages = (await client.get(url)).json()
    assert messages[0]["attachments"][0]["extraction_status"] == "empty"
    assert messages[1]["status"] == "failed"
    assert "Читаемый текст не найден" in messages[1]["error"]
    assert messages[1]["result"] is None


@pytest.mark.parametrize("route", ["chat", "knowledge"])
@pytest.mark.parametrize("encoding", ["cp1251", "utf-16", "utf-8-sig"])
async def test_text_encoding_on_both_routes(client, route, encoding):
    url = await upload_url(client, route)
    response = await client.post(
        url,
        files=[
            ("files", ("synthetic.txt", "Приговор районного суда".encode(encoding), "text/plain"))
        ],
    )
    assert response.status_code == (202 if route == "chat" else 200)
    if route == "chat":
        messages = (await client.get(url)).json()
        assert messages[0]["attachments"][0]["extraction_status"] == "ok"
    else:
        assert response.json()["items"][0]["extraction_status"] == "ok"


@pytest.mark.parametrize("route", ["chat", "knowledge"])
async def test_dotx_has_real_admission_and_reader_on_both_routes(client, route):
    types = CONTENT_TYPES.replace(
        b"wordprocessingml.document.main+xml", b"wordprocessingml.template.main+xml"
    )
    raw = archive({"[Content_Types].xml": types})
    url = await upload_url(client, route)
    response = await client.post(
        url, files=[("files", ("synthetic.DOTX", raw, "application/octet-stream"))]
    )
    assert response.status_code == (202 if route == "chat" else 200)


async def test_invalid_second_file_rolls_back_batch_and_cleans_new_files(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    response = await client.post(
        "/api/knowledge/verdicts/upload",
        files=[
            ("files", ("valid.txt", b"Valid synthetic judgment", "text/plain")),
            ("files", ("empty.txt", b"", "text/plain")),
        ],
    )
    assert response.status_code == 422
    assert (await client.get("/api/knowledge/verdicts")).json()["total"] == 0
    assert list(tmp_path.iterdir()) == []
