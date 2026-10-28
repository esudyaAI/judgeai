import asyncio
import importlib
from pathlib import Path

from src.application.document_reading import ReadDocument
from src.domain.documents import MAX_TEXT_CHARACTERS, ExtractedDocument, classify_pages
from src.domain.uploads import UploadRejected
from src.infrastructure.document_readers import read_text
from src.infrastructure.word_reader import read_word


def _read_pdf_file(path: Path) -> ExtractedDocument:
    pdfplumber = importlib.import_module("pdfplumber")
    pages: list[str] = []
    unreadable = []
    size = 0
    with pdfplumber.open(str(path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ""
                size += len(text)
                if size > MAX_TEXT_CHARACTERS:
                    raise UploadRejected("reading_limit", "Текст документа слишком большой")
                pages.append(text)
            except UploadRejected:
                raise
            except Exception:
                unreadable.append(number)
                pages.append("")
    missing = tuple(number for number, text in enumerate(pages, 1) if not text.strip())
    issues = []
    if len(missing) > len(unreadable):
        issues.append("no_text_layer")
    if unreadable:
        issues.append("unreadable_pages")
    return ExtractedDocument(
        "\n".join(pages), len(pages), classify_pages(pages), tuple(issues), missing
    )


_READERS = {
    ".txt": read_text,
    ".md": read_text,
    ".docx": read_word,
    ".dotx": read_word,
    ".pdf": _read_pdf_file,
}


async def extract_document(path: Path) -> ExtractedDocument:
    reader = _READERS.get(path.suffix.lower())
    return await asyncio.to_thread(
        ReadDocument().execute, None if reader is None else lambda: reader(path)
    )


async def extract_text_from_file(path: Path) -> str:
    """Backward-compatible helper used by the knowledge-base upload."""
    return (await extract_document(path)).text
