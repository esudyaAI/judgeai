"""T17.5: both upload routes refuse an oversized batch before storing anything."""

from pathlib import Path

import pytest

from src.config import settings
from tests.test_docx_uploads import upload_url


def _texts(count: int, size: int = 0) -> list[tuple]:
    body = "Синтетический текст приговора номер {}. ".format
    return [
        ("files", (f"f{i}.txt", (body(i) + "я" * size).encode(), "text/plain"))
        for i in range(count)
    ]


def _stored() -> set[Path]:
    return set(Path(settings.UPLOAD_DIR).glob("*"))


@pytest.mark.parametrize("route", ["chat", "knowledge"])
async def test_batch_at_the_limit_is_accepted(client, route, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 2)
    url = await upload_url(client, route)
    response = await client.post(url, files=_texts(2))
    assert response.status_code == (202 if route == "chat" else 200)


@pytest.mark.parametrize("route", ["chat", "knowledge"])
async def test_too_many_files_are_refused_before_storing(client, route, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 2)
    url = await upload_url(client, route)
    before = _stored()
    response = await client.post(url, files=_texts(3))
    assert response.status_code == 413
    assert "не больше 2" in response.json()["detail"]
    assert _stored() == before
    if route == "chat":
        assert (await client.get(url)).json() == []


@pytest.mark.parametrize("route", ["chat", "knowledge"])
async def test_total_size_over_limit_is_refused_before_storing(client, route, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_REQUEST_MB", 1)
    url = await upload_url(client, route)
    before = _stored()
    # Each file is below the per-file cap; only their sum is over the request limit.
    response = await client.post(url, files=_texts(2, size=300_000))
    assert response.status_code == 413
    assert "1 МБ" in response.json()["detail"]
    assert _stored() == before


async def test_foreign_chat_is_still_not_found_for_an_oversized_batch(client, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 1)
    response = await client.post("/api/chats/999999/messages", files=_texts(2))
    assert response.status_code == 404
