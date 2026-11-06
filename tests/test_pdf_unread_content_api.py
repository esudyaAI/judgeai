"""T17.4: both upload routes keep a PDF with unread attachments as an explicit partial reading."""

import pytest

from tests.test_docx_uploads import upload_url
from tests_reading.test_pdf_unread_content import ATTACHMENT


@pytest.mark.parametrize("route", ["chat", "knowledge"])
async def test_pdf_with_attachment_is_accepted_as_partial(client, route):
    url = await upload_url(client, route)
    response = await client.post(
        url, files=[("files", ("synthetic.pdf", ATTACHMENT, "application/pdf"))]
    )
    assert response.status_code == (202 if route == "chat" else 200)
    if route == "chat":
        attachment = (await client.get(url)).json()[0]["attachments"][0]
        assert attachment["extraction_status"] == "partial"
    else:
        item = response.json()["items"][0]
        assert item["extraction_status"] == "partial"
        assert item["extraction_issues"] == ["pdf_attachments"]
        assert any("Вложенные" in warning for warning in item["warnings"])
