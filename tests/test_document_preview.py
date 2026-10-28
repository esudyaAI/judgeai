"""Real authorization, paths, original delivery and conversion bindings."""

from pathlib import Path

from src.config import settings
from src.db.models import Attachment, Chat, Message
from src.db.session import async_session_factory
from src.infrastructure.preview_spool import PreviewSpool, write_status
from tests.test_auth import account, anonymous, login


async def seed(owner, filename="document.pdf", path=None):
    path = path or Path(settings.UPLOAD_DIR) / filename
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"%PDF-synthetic")
    async with async_session_factory() as db:
        chat = Chat(owner_id=owner)
        db.add(chat)
        await db.flush()
        message = Message(chat_id=chat.id, role="user", status="completed")
        db.add(message)
        await db.flush()
        attachment = Attachment(message_id=message.id, filename=filename, stored_path=str(path))
        db.add(attachment)
        await db.commit()
        return chat.id, attachment.id, path


async def test_attachment_delivery_owner_headers_and_revocation(tmp_path, monkeypatch):
    alice = await account("alice")
    await account("bob")
    chat, attachment, _ = await seed(alice)
    url = f"/api/chats/{chat}/attachments/{attachment}/file"
    async with anonymous() as a, anonymous() as b:
        assert (await a.get(url)).status_code == 401
        await login(a, "alice")
        await login(b, "bob")
        assert (await b.get(url)).status_code == 404
        response = await a.get(url)
        assert response.status_code == 200
        assert response.content == b"%PDF-synthetic"
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith("inline")
        assert (
            (await a.get(url + "?download=true"))
            .headers["content-disposition"]
            .startswith("attachment")
        )
        assert (
            await a.get(f"/api/chats/{chat + 1}/attachments/{attachment}/file")
        ).status_code == 404
        assert (await a.delete(f"/api/chats/{chat}")).status_code == 200
        assert (await a.get(url)).status_code == 404


async def test_preview_tokens_are_owner_and_live_attachment_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_PREVIEW_DIR", str(tmp_path / "previews"))
    alice = await account("alice")
    await account("bob")
    chat, attachment, source = await seed(alice, "document.docx")
    async with anonymous() as a, anonymous() as b:
        await login(a, "alice")
        await login(b, "bob")
        url = f"/api/chats/{chat}/attachments/{attachment}/preview"
        assert (await b.post(url)).status_code == 404
        csrf = a.headers.pop("X-CSRF-Token")
        assert (await a.post(url)).status_code == 403
        a.headers["X-CSRF-Token"] = csrf
        response = await a.post(url)
        assert response.status_code == 202
        job = response.json()
        assert set(job) == {"id", "filename", "status", "error"}
        token_url = "/api/document-previews/" + job["id"]
        assert (await b.get(token_url)).status_code == 404
        assert (await b.get(token_url + "/file")).status_code == 404
        assert (await a.get(token_url + "/file")).status_code == 404
        spool = PreviewSpool(tmp_path / "previews")
        metadata = spool.get(job["id"], alice)
        metadata["status"] = "ready"
        directory = spool.root / job["id"]
        (directory / "preview.pdf").write_bytes(b"%PDF-synthetic-converted")
        write_status(directory, metadata)
        assert (await a.get(token_url + "/file")).content == b"%PDF-synthetic-converted"
        assert (await a.delete(f"/api/chats/{chat}")).status_code == 200
        assert (await a.get(token_url)).status_code == 404
        assert (await a.get(token_url + "/file")).status_code == 404


async def test_unsafe_stored_path_is_never_served(tmp_path):
    owner = await account("alice")
    chat, attachment, _ = await seed(owner, path=tmp_path / "outside.pdf")
    async with anonymous() as client:
        await login(client, "alice")
        assert (
            await client.get(f"/api/chats/{chat}/attachments/{attachment}/file")
        ).status_code == 404


async def test_staged_word_validates_upload_and_leaves_no_original(tmp_path, monkeypatch, client):
    from tests_uploads.test_docx_guard import archive

    monkeypatch.setattr(settings, "DOCUMENT_PREVIEW_DIR", str(tmp_path / "previews"))
    before = set(Path(settings.UPLOAD_DIR).glob("*"))
    invalid = await client.post(
        "/api/document-previews", files={"file": ("fake.docx", b"not a Word file")}
    )
    assert invalid.status_code == 415
    response = await client.post("/api/document-previews", files={"file": ("safe.docx", archive())})
    assert response.status_code == 202
    assert (await client.get("/api/document-previews/" + response.json()["id"])).status_code == 200
    assert set(Path(settings.UPLOAD_DIR).glob("*")) == before
    assert (
        await client.post("/api/document-previews", files={"file": ("old.doc", b"legacy")})
    ).status_code == 415
