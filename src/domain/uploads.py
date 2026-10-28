"""Pure admission policies for supported, bounded document subsets."""

from dataclasses import dataclass, fields


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _check_positive_limits(instance, label):
    if any(
        type(getattr(instance, item.name)) is not int or getattr(instance, item.name) <= 0
        for item in fields(instance)
    ):
        raise ValueError(f"{label} limits must be positive integers")


@dataclass(frozen=True)
class DocxLimits:
    max_compressed_bytes: int = 50 * 1024 * 1024
    max_entries: int = 512
    max_directory_bytes: int = 256 * 1024
    max_total_bytes: int = 100 * 1024 * 1024
    max_member_bytes: int = 20 * 1024 * 1024
    max_xml_bytes: int = 8 * 1024 * 1024
    max_ratio: int = 200
    max_xml_depth: int = 128
    max_xml_elements: int = 200000

    def __post_init__(self):
        _check_positive_limits(self, "DOCX")


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    size: int
    compressed_size: int
    method: int
    encrypted: bool
    symlink: bool
    zip_version: int


@dataclass(frozen=True)
class DocxInspection:
    entries: int
    uncompressed_bytes: int


def require_budget(value: int, maximum: int) -> None:
    if value > maximum:
        raise UploadRejected("docx_limit", "DOCX превышает допустимые пределы обработки")


def check_directory(entries: int, directory_bytes: int, source_bytes: int, limits: DocxLimits):
    require_budget(source_bytes, limits.max_compressed_bytes)
    require_budget(entries, limits.max_entries)
    require_budget(directory_bytes, limits.max_directory_bytes)


def check_entry(entry: ArchiveEntry, limits: DocxLimits):
    name = entry.name
    parts = name.rstrip("/").split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or any(ord(character) < 32 for character in name)
        or any(part in {"", ".", ".."} for part in parts)
        or entry.symlink
    ):
        raise UploadRejected("docx_unsafe", "DOCX содержит небезопасные элементы")
    if entry.encrypted or entry.method not in {0, 8} or entry.zip_version > 20:
        raise UploadRejected(
            "docx_unsupported", "Шифрование или такой способ сжатия DOCX не поддерживается"
        )
    if name.lower().endswith("vbaproject.bin"):
        raise UploadRejected("docx_unsafe", "Документы с макросами не поддерживаются")
    if entry.size < 0 or entry.compressed_size < 0:
        raise UploadRejected("docx_invalid", "Файл DOCX повреждён")
    require_budget(entry.size, limits.max_member_bytes)
    require_budget(entry.size, entry.compressed_size * limits.max_ratio)
    if name.lower().endswith((".xml", ".rels")):
        require_budget(entry.size, limits.max_xml_bytes)


@dataclass(frozen=True)
class PdfLimits:
    max_source_bytes: int = 50 * 1024 * 1024
    max_pages: int = 200
    max_objects: int = 20000
    max_stream_bytes: int = 8 * 1024 * 1024
    max_total_decoded_bytes: int = 32 * 1024 * 1024
    max_ratio: int = 200
    max_nodes: int = 200000
    max_depth: int = 64
    max_filters: int = 4
    max_page_points: int = 14400
    max_image_pixels: int = 40000000
    max_memory_bytes: int = 512 * 1024 * 1024
    max_cpu_seconds: int = 3
    max_wall_seconds: int = 6

    def __post_init__(self):
        _check_positive_limits(self, "PDF")


@dataclass(frozen=True)
class PdfInspection:
    pages: int
    objects: int
    decoded_bytes: int


def reject_pdf(code: str) -> UploadRejected:
    messages = {
        "pdf_invalid": "PDF повреждён или не поддерживается",
        "pdf_encrypted": "Зашифрованные PDF не поддерживаются",
        "pdf_limit": "PDF превышает допустимые пределы обработки",
        "pdf_busy": "Проверка PDF сейчас занята; попробуйте позже",
        "pdf_unavailable": "Проверка PDF недоступна; попробуйте позже",
    }
    if not isinstance(code, str) or code not in messages:
        code = "pdf_unavailable"
    return UploadRejected(code, messages[code])


def require_pdf_budget(value: int | float, maximum: int) -> None:
    if value > maximum:
        raise reject_pdf("pdf_limit")
