"""Document reading results and user-safe diagnostics, independent of parsers and HTTP."""

from dataclasses import dataclass

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
}


def reading_warnings(document: ExtractedDocument) -> list[str]:
    messages = [_MESSAGES[issue] for issue in document.issues if issue in _MESSAGES]
    if document.unread_pages:
        messages.append("Unread pages: " + ", ".join(map(str, document.unread_pages)))
    return messages


class UnreadableInput(ValueError):
    """No document text or question can ground an analysis."""
