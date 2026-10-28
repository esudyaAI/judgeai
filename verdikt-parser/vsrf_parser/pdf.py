"""Скачивание PDF-актов и извлечение текстового слоя (PyMuPDF + OCR-fallback)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .client import VSRFClient

log = logging.getLogger("vsrf_parser.pdf")

PDF_MAGIC = b"%PDF"
TEXT_LAYER_MIN_CHARS_PER_PAGE = 80


@dataclass(slots=True)
class PdfTextResult:
    text: str
    pages: int
    has_text_layer: bool
    ocr_used: bool = False
    ocr_available: bool = True

    @property
    def needs_ocr(self) -> bool:
        return not self.has_text_layer and not self.ocr_used


def is_valid_pdf_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == PDF_MAGIC
    except OSError:
        return False


def download_pdf(client: VSRFClient, stor_id: str, dest: Path) -> str:
    """Скачивает PDF; возвращает 'downloaded' | 'exists' | 'failed'."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and is_valid_pdf_file(dest):
        return "exists"
    data = client.fetch_pdf(stor_id)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return "downloaded"


def _render_page_png(page: pymupdf.Page, dpi: int) -> bytes:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return pix.tobytes("png")


def _ocr_pdf(doc: pymupdf.Document, lang: str) -> str:
    try:
        import io

        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    parts: list[str] = []
    for page in doc:
        png = _render_page_png(page, dpi=300)
        img = Image.open(io.BytesIO(png))
        parts.append(pytesseract.image_to_string(img, lang=lang))
    return "\n".join(parts)


def extract_text(pdf_path: Path, ocr: bool = True, ocr_lang: str = "rus") -> PdfTextResult:
    """Извлекает текст из PDF; при отсутствии текстового слоя пробует OCR."""
    doc = pymupdf.open(pdf_path)
    try:
        text = "\n".join(page.get_text() for page in doc)
        pages = doc.page_count
        threshold = max(1, pages) * TEXT_LAYER_MIN_CHARS_PER_PAGE
        if len(text.strip()) >= threshold:
            return PdfTextResult(text=text, pages=pages, has_text_layer=True)
        if not ocr:
            return PdfTextResult(text=text, pages=pages, has_text_layer=False)
        log.info(
            "Текстовый слой отсутствует (%d симв. на %d стр.), пробую OCR: %s",
            len(text.strip()), pages, pdf_path.name,
        )
        ocr_text = _ocr_pdf(doc, ocr_lang)
        if ocr_text.strip():
            return PdfTextResult(
                text=ocr_text, pages=pages, has_text_layer=False, ocr_used=True
            )
        return PdfTextResult(
            text=text, pages=pages, has_text_layer=False, ocr_available=False
        )
    finally:
        doc.close()


def save_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


WHITESPACE_RE = re.compile(r"[ \t]+")
