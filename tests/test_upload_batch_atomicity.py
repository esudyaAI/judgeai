"""T17.6: a batch is admitted or refused as a whole on both upload routes."""

import pytest

from src.config import settings
from tests.test_docx_uploads import upload_url

_ROUTES = {"chat": "src.api.chats", "knowledge": "src.api.knowledge"}


def _text(name: str, body: bytes = b"Synthetic judgment text") -> tuple:
    return ("files", (name, body, "text/plain"))


@pytest.mark.parametrize("route", list(_ROUTES))
async def test_unsupported_later_file_refuses_the_batch_before_storing_anything(
    client, route, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    async def must_not_store(file):
        pytest.fail("no file may be stored when the batch has an unsupported format")

    monkeypatch.setattr(f"{_ROUTES[route]}.save_upload_file", must_not_store)
    url = await upload_url(client, route)
    response = await client.post(url, files=[_text("valid.txt"), _text("macro.exe")])
    assert response.status_code == 415
    assert ".exe" in response.json()["detail"]
    assert list(tmp_path.iterdir()) == []


async def test_chat_batch_failing_on_a_later_file_leaves_no_files_and_no_message(
    client, monkeypatch, tmp_path
):
    """The size of a later file is only known while streaming it to disk."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "UPLOAD_MAX_MB", 1)
    url = await upload_url(client, "chat")
    response = await client.post(
        url,
        files=[_text("valid.txt"), _text("large.txt", b"x" * (1024 * 1024 + 1))],
    )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []
    assert (await client.get(url)).json() == []
