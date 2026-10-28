"""Bounded ZIP/XML inspection; never extracts package members to the filesystem."""

import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import BinaryIO
from xml.parsers import expat

from src.domain.uploads import (
    ArchiveEntry,
    DocxInspection,
    DocxLimits,
    UploadRejected,
    check_directory,
    check_entry,
    require_budget,
)

_CHUNK = 64 * 1024
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types}"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships}"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
_MAIN_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
}
_WORD_NAMESPACES = {_WORD_NS, "http://purl.oclc.org/ooxml/wordprocessingml/main}"}
_OFFICE_RELS = {
    _OFFICE_REL,
    "http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
}


def invalid() -> UploadRejected:
    return UploadRejected("docx_invalid", "Файл не является поддерживаемым документом Word")


def _directory_preflight(source: BinaryIO, limits: DocxLimits) -> int:
    source.seek(0, 2)
    size = source.tell()
    check_directory(0, 0, size, limits)
    source.seek(0)
    if source.read(4) != b"PK\x03\x04":
        raise invalid()
    source.seek(max(0, size - 65557))
    tail = source.read(65557)
    position = len(tail)
    while True:
        position = tail.rfind(b"PK\x05\x06", 0, position)
        if position < 0:
            raise invalid()
        if position + 22 <= len(tail):
            values = struct.unpack_from("<4s4H2LH", tail, position)
            if position + 22 + values[-1] == len(tail):
                break
    _, disk, directory_disk, disk_entries, entries, directory_bytes, offset, _ = values
    if (
        disk
        or directory_disk
        or disk_entries != entries
        or entries == 65535
        or directory_bytes == 0xFFFFFFFF
        or offset == 0xFFFFFFFF
        or offset + directory_bytes > size - len(tail) + position
    ):
        raise invalid()
    check_directory(entries, directory_bytes, size, limits)
    source.seek(0)
    return entries


@dataclass
class _XmlFacts:
    root: str | None = None
    body: bool = False
    main_type: str | None = None
    office_targets: list[tuple[str, str | None]] = field(default_factory=list)
    overrides: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)


class _XmlReader:
    def __init__(self, limits: DocxLimits, element_counter: list[int]):
        self.limits = limits
        self.element_counter = element_counter
        self.depth = 0
        self.facts = _XmlFacts()
        self.parser = expat.ParserCreate(namespace_separator="}")
        self.parser.StartElementHandler = self.start
        self.parser.EndElementHandler = self.end
        self.parser.StartDoctypeDeclHandler = self.forbidden
        self.parser.EntityDeclHandler = self.forbidden
        self.parser.ExternalEntityRefHandler = self.forbidden

    def forbidden(self, *args):
        raise UploadRejected("docx_unsafe", "Такие XML-объявления в DOCX не поддерживаются")

    def start(self, name, attrs):
        self.depth += 1
        self.element_counter[0] += 1
        require_budget(self.depth, self.limits.max_xml_depth)
        require_budget(self.element_counter[0], self.limits.max_xml_elements)
        if self.depth == 1:
            self.facts.root = name
        if self.depth == 2 and name in {namespace + "body" for namespace in _WORD_NAMESPACES}:
            self.facts.body = True
        if name in {_CT_NS + "Override", _CT_NS + "Default"}:
            content_type = attrs.get("ContentType", "")
            if "macroenabled" in content_type.lower() or "vbaproject" in content_type.lower():
                raise UploadRejected("docx_unsafe", "Документы с макросами не поддерживаются")
            mapping = self.facts.overrides if name == _CT_NS + "Override" else self.facts.defaults
            key = attrs.get(
                "PartName" if name == _CT_NS + "Override" else "Extension", ""
            ).casefold()
            if not key or key in mapping:
                raise invalid()
            mapping[key] = content_type.lower()
            if name == _CT_NS + "Override" and attrs.get("PartName") == "/word/document.xml":
                if self.facts.main_type is not None:
                    raise invalid()
                self.facts.main_type = content_type
        if name == _REL_NS + "Relationship" and attrs.get("Type") in _OFFICE_RELS:
            self.facts.office_targets.append((attrs.get("Target", ""), attrs.get("TargetMode")))

    def end(self, name):
        self.depth -= 1

    def feed(self, data: bytes, final: bool = False):
        self.parser.Parse(data, final)


class DocxInspector:
    def inspect(self, source: BinaryIO, limits: DocxLimits) -> DocxInspection:
        try:
            expected_entries = _directory_preflight(source, limits)
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) != expected_entries:
                    raise invalid()
                check_directory(len(entries), 0, 0, limits)
                seen = set()
                total_declared = 0
                for entry in entries:
                    name = entry.filename.casefold()
                    if name in seen:
                        raise UploadRejected("docx_unsafe", "DOCX содержит повторяющиеся элементы")
                    seen.add(name)
                    check_entry(
                        ArchiveEntry(
                            entry.orig_filename,
                            entry.file_size,
                            entry.compress_size,
                            entry.compress_type,
                            bool(entry.flag_bits & 1),
                            stat.S_ISLNK(entry.external_attr >> 16),
                            entry.extract_version,
                        ),
                        limits,
                    )
                    total_declared += entry.file_size
                    require_budget(total_declared, limits.max_total_bytes)
                xml_facts = {}
                total_read = 0
                elements = [0]
                content_entry = next(
                    (entry for entry in entries if entry.filename == "[Content_Types].xml"), None
                )
                if content_entry is None:
                    raise invalid()
                ordered_entries = [content_entry] + [
                    entry for entry in entries if entry is not content_entry
                ]
                types = _XmlFacts()
                for entry in ordered_entries:
                    content_type = types.overrides.get(
                        "/" + entry.filename.casefold(),
                        types.defaults.get(entry.filename.rsplit(".", 1)[-1].casefold(), ""),
                    )
                    is_xml = (
                        entry.filename.lower().endswith((".xml", ".rels"))
                        or content_type.endswith("+xml")
                        or content_type in {"application/xml", "text/xml"}
                    )
                    if is_xml:
                        require_budget(entry.file_size, limits.max_xml_bytes)
                    parser = _XmlReader(limits, elements) if is_xml else None
                    member_read = 0
                    with archive.open(entry) as member:
                        while chunk := member.read(_CHUNK):
                            member_read += len(chunk)
                            total_read += len(chunk)
                            require_budget(member_read, limits.max_member_bytes)
                            require_budget(total_read, limits.max_total_bytes)
                            if parser:
                                require_budget(member_read, limits.max_xml_bytes)
                                parser.feed(chunk)
                    if member_read != entry.file_size:
                        raise invalid()
                    if parser:
                        parser.feed(b"", True)
                        xml_facts[entry.filename] = parser.facts
                        if entry is content_entry:
                            types = parser.facts
                self._check_package(xml_facts)
                return DocxInspection(len(entries), total_read)
        except UploadRejected:
            raise
        except (
            zlib.error,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            expat.ExpatError,
            RuntimeError,
            EOFError,
            ValueError,
            NotImplementedError,
            struct.error,
        ):
            raise invalid() from None

    @staticmethod
    def _check_package(parts: dict[str, _XmlFacts]):
        content_types = parts.get("[Content_Types].xml")
        relationships = parts.get("_rels/.rels")
        main = parts.get("word/document.xml")
        if (
            content_types is None
            or content_types.root != _CT_NS + "Types"
            or content_types.main_type not in _MAIN_TYPES
            or relationships is None
            or relationships.root != _REL_NS + "Relationships"
            or len(relationships.office_targets) != 1
            or relationships.office_targets[0][0] not in {"word/document.xml", "/word/document.xml"}
            or relationships.office_targets[0][1] not in {None, "Internal"}
            or main is None
            or main.root not in {namespace + "document" for namespace in _WORD_NAMESPACES}
            or not main.body
        ):
            raise invalid()
