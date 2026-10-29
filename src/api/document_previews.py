"""Authenticated document delivery and asynchronous Word preview requests."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.api.deps import CurrentUser, DbSession
from src.application.document_preview import DocumentPreview, PreviewNotFound, PreviewUnavailable
from src.config import settings
from src.infrastructure.attachment_repository import SqlAttachmentRepository
from src.infrastructure.preview_spool import AsyncPreviewJobs, PreviewSpool
from src.services.file_reader import save_upload_file

router = APIRouter()
_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'self'",
    "Referrer-Policy": "no-referrer",
}


def _service(db) -> DocumentPreview:
    if not settings.DOCUMENT_PREVIEW_DIR:
        raise HTTPException(503, "Сервис просмотра Word не настроен")
    return DocumentPreview(
        SqlAttachmentRepository(db, Path(settings.UPLOAD_DIR)),
        AsyncPreviewJobs(PreviewSpool(Path(settings.DOCUMENT_PREVIEW_DIR))),
    )


def _public(job: dict) -> dict:
    return {key: job[key] for key in ("id", "filename", "status", "error")}


def _file(path: Path, filename: str, *, inline: bool = True) -> FileResponse:
    suffix = path.suffix.lower()
    media = (
        "application/pdf"
        if suffix == ".pdf"
        else "text/plain"
        if suffix in {".txt", ".md"}
        else "application/octet-stream"
    )
    headers = dict(_HEADERS)
    if suffix in {".txt", ".md"}:
        headers["Content-Security-Policy"] += "; sandbox"
    return FileResponse(
        path,
        media_type=media,
        filename=filename,
        headers=headers,
        content_disposition_type="inline"
        if inline and suffix in {".pdf", ".txt", ".md"}
        else "attachment",
    )


@router.get("/chats/{chat_id}/attachments/{attachment_id}/file")
async def original(
    chat_id: int, attachment_id: int, db: DbSession, user: CurrentUser, download: bool = False
):
    try:
        source = await SqlAttachmentRepository(db, Path(settings.UPLOAD_DIR)).get(
            user.user_id, chat_id, attachment_id
        )
        return _file(Path(source.path), source.filename, inline=not download)
    except PreviewNotFound:
        raise HTTPException(404, "Документ не найден") from None


@router.post("/chats/{chat_id}/attachments/{attachment_id}/preview", status_code=202)
async def prepare(chat_id: int, attachment_id: int, db: DbSession, user: CurrentUser):
    try:
        return _public(await _service(db).prepare(user.user_id, chat_id, attachment_id))
    except PreviewNotFound:
        raise HTTPException(404, "Документ не найден") from None
    except PreviewUnavailable as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/document-previews", status_code=202)
async def stage(db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    service = _service(db)
    if Path(file.filename or "").suffix.lower() not in {".docx", ".dotx"}:
        raise HTTPException(415, "Просмотр Word поддерживается для DOCX и DOTX")
    path, _ = await save_upload_file(file)
    try:
        job = await service.jobs.create(
            str(path), file.filename or "document.docx", user.user_id, None
        )
        return _public(job)
    except PreviewUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        path.unlink(missing_ok=True)


@router.get("/document-previews/{token}")
async def status(token: str, db: DbSession, user: CurrentUser):
    try:
        return _public(await _service(db).status(user.user_id, token))
    except PreviewNotFound:
        raise HTTPException(404, "Срок просмотра истёк или документ не найден") from None


@router.get("/document-previews/{token}/file")
async def rendered(token: str, db: DbSession, user: CurrentUser):
    try:
        service = _service(db)
        job = await service.status(user.user_id, token)
        path = await service.pdf(user.user_id, token)
        return _file(Path(path), Path(job["filename"]).stem + ".pdf")
    except PreviewNotFound:
        raise HTTPException(404, "Просмотр пока недоступен") from None
