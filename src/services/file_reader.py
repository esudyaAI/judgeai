import asyncio
import uuid
from collections.abc import Sequence
from pathlib import Path

from fastapi import HTTPException, UploadFile

from src.application.upload_validation import ValidateUpload
from src.config import settings
from src.domain.uploads import (
    DocxLimits,
    PdfLimits,
    UploadBatchLimits,
    UploadRejected,
    check_upload_batch,
)
from src.infrastructure.docx_inspector import DocxInspector
from src.infrastructure.pdf_process import PdfProcessInspector

_CHUNK = 1024 * 1024


def validate_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=415,
            detail=f"Формат «{suffix or 'без расширения'}» не поддерживается. Допустимо: {allowed}",
        )
    return suffix


def validate_upload_batch(files: Sequence[UploadFile]) -> None:
    """Refuse the whole request by count, total size or a format before storing any file."""
    per_file = settings.UPLOAD_MAX_MB * 1024 * 1024
    # An unknown size must not shrink the total: count it as the largest allowed file.
    sizes = [per_file if file.size is None else file.size for file in files]
    limits = UploadBatchLimits(
        max_files=settings.UPLOAD_MAX_FILES,
        max_total_bytes=settings.UPLOAD_MAX_REQUEST_MB * 1024 * 1024,
    )
    try:
        check_upload_batch(sizes, limits)
    except UploadRejected as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    for file in files:
        validate_extension(file.filename)


def _validate_stored_document(path: Path) -> None:
    validator = ValidateUpload(
        DocxInspector(),
        DocxLimits(max_compressed_bytes=settings.UPLOAD_MAX_MB * 1024 * 1024),
        pdf_inspector=PdfProcessInspector(),
        pdf_limits=PdfLimits(max_source_bytes=settings.UPLOAD_MAX_MB * 1024 * 1024),
    )
    with path.open("rb") as source:
        validator.execute(source, path.suffix)


async def save_upload_file(file: UploadFile) -> tuple[Path, int]:
    """Stream the upload to disk with a size cap; the file name on disk is random."""
    suffix = validate_extension(file.filename)
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid.uuid4()}{suffix}"
    limit = settings.UPLOAD_MAX_MB * 1024 * 1024

    size = 0
    try:
        with stored_path.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Файл «{file.filename}» больше {settings.UPLOAD_MAX_MB} МБ",
                    )
                out.write(chunk)
        if suffix in {".docx", ".dotx", ".pdf"}:
            try:
                await asyncio.to_thread(_validate_stored_document, stored_path)
            except UploadRejected as exc:
                status = 413 if exc.code in {"docx_limit", "pdf_limit"} else 415
                if exc.code in {"pdf_unavailable", "pdf_busy"}:
                    status = 503
                raise HTTPException(status, str(exc)) from None
    except BaseException:
        stored_path.unlink(missing_ok=True)
        raise

    return stored_path, size
