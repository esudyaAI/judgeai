"""Document reading results and user-safe diagnostics, independent of parsers and HTTP."""

from dataclasses import dataclass, replace

MAX_TEXT_CHARACTERS = 2_000_000
MAX_TEXT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    page_count: int | None
    status: str
    issues: tuple[str, ...] = ()
    unread_pages: tuple[int, ...] = ()
    encoding: str | None = None


def classify_pages(page_texts: list[str]) -> str:
    if not page_texts:
        return "empty"
    count = sum(bool(text.strip()) for text in page_texts)
    return "empty" if count == 0 else "ok" if count == len(page_texts) else "partial"


_MESSAGES = {
    "unsupported_format": (
        "Этот вариант файла не поддерживается. Сохраните его в TXT, DOCX или PDF."
    ),
    "invalid_encoding": "Кодировка текста неверна или неоднозначна. Сохраните файл в UTF-8.",
    "binary_text": "Файл содержит двоичные данные, а не обычный текст.",
    "resource_limit": "Документ превышает допустимые пределы чтения.",
    "no_text_layer": (
        "На некоторых страницах PDF нет текста. Нужно распознавание (OCR) или другая копия."
    ),
    "unreadable_pages": "Некоторые страницы PDF не удалось прочитать. Загрузите другую копию.",
    "unsupported_content": (
        "Изображения и встроенные объекты не прочитаны; текст документа неполный."
    ),
    "tracked_changes": "В документе есть неподтверждённые исправления. Загрузите итоговую версию.",
    "invalid_document": "Документ повреждён, зашифрован или не поддерживается.",
    "empty_document": "В документе не найден пригодный текст.",
    "pdf_attachments": ("Вложенные в PDF файлы не прочитаны; загрузите их отдельными документами."),
    "pdf_portfolio": (
        "Это PDF-портфель: прочитана только обложка, входящие в него документы — нет. "
        "Загрузите их отдельными файлами."
    ),
    "xfa_form": ("Содержимое XFA-формы в PDF не прочитано; текст документа может быть неполным."),
}

# T17.4: parts present in a document but not read by text extraction, in report order.
UNREAD_CONTENT = ("pdf_portfolio", "pdf_attachments", "xfa_form")


def with_unread_content(document: ExtractedDocument, found: set[str]) -> ExtractedDocument:
    """Mark content that was present but not read; a complete reading becomes partial.

    A portfolio already says its documents were not read, so its attachments are not
    reported twice. Empty and failed readings keep their status: unread parts never make
    a document usable.
    """
    unknown = found - set(UNREAD_CONTENT)
    if unknown:
        raise ValueError(f"unknown unread content: {sorted(unknown)}")
    if "pdf_portfolio" in found:
        found = found - {"pdf_attachments"}
    added = tuple(
        issue for issue in UNREAD_CONTENT if issue in found and issue not in document.issues
    )
    if not found:
        return document
    status = "partial" if document.status == "ok" else document.status
    return replace(document, status=status, issues=document.issues + added)


def reading_warnings(document: ExtractedDocument) -> list[str]:
    messages = [_MESSAGES[issue] for issue in document.issues if issue in _MESSAGES]
    if document.unread_pages:
        messages.append("Unread pages: " + ", ".join(map(str, document.unread_pages)))
    return messages


class UnreadableInput(ValueError):
    """No document text or question can ground an analysis."""
