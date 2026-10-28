import io
import struct
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.application.upload_validation import ValidateUpload
from src.domain.uploads import DocxLimits, UploadRejected
from src.infrastructure.docx_inspector import DocxInspector

CONTENT_TYPES = (
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Override PartName="/word/document.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.'
    b'wordprocessingml.document.main+xml"/></Types>'
)
RELS = (
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    b'officeDocument/2006/relationships/officeDocument" '
    b'Target="word/document.xml"/></Relationships>'
)
DOCUMENT = (
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b"<w:body><w:p><w:r><w:t>Synthetic case.</w:t></w:r></w:p></w:body></w:document>"
)


def archive(overrides=None, *, extra=None, compression=zipfile.ZIP_DEFLATED):
    entries = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": RELS,
        "word/document.xml": DOCUMENT,
    }
    entries.update(overrides or {})
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=compression) as z:
        for name, payload in list(entries.items()) + list(extra or []):
            if payload is not None:
                z.writestr(name, payload)
    return data.getvalue()


class DocxGuardTests(unittest.TestCase):
    def validate(self, raw, limits=None):
        stream = io.BytesIO(raw)
        result = ValidateUpload(DocxInspector(), limits or DocxLimits()).execute(stream, ".docx")
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(stream.getvalue(), raw)
        return result

    def test_valid_docx_is_inspected_without_changing_bytes(self):
        raw = archive()
        self.assertEqual(self.validate(raw).entries, 3)
        self.assertEqual(
            self.validate(raw).uncompressed_bytes, len(CONTENT_TYPES + RELS + DOCUMENT)
        )

    def test_other_formats_do_not_use_docx_inspector(self):
        class Never:
            def inspect(self, source, limits):
                raise AssertionError("DOCX inspector called for another format")

        self.assertIsNone(
            ValidateUpload(Never(), DocxLimits()).execute(io.BytesIO(b"text"), ".txt")
        )

    def test_renamed_and_truncated_files_are_rejected(self):
        for raw in (b"%PDF-1.7 synthetic", b"not a docx", archive()[:-10]):
            with self.subTest(raw=raw[:10]), self.assertRaises(UploadRejected):
                self.validate(raw)

    def test_package_requires_content_types_main_document_and_root_relationship(self):
        for part in ("[Content_Types].xml", "word/document.xml", "_rels/.rels"):
            with self.subTest(part=part), self.assertRaises(UploadRejected):
                self.validate(archive({part: None}))
        with self.assertRaises(UploadRejected):
            self.validate(archive({"word/document.xml": b"<notword/>"}))

    def test_preflight_rejects_member_count_and_directory_size_before_zipfile_parsing(self):
        raw = archive()
        for limits in (
            replace(DocxLimits(), max_entries=2),
            replace(DocxLimits(), max_directory_bytes=1),
        ):
            with patch(
                "src.infrastructure.docx_inspector.zipfile.ZipFile",
                side_effect=AssertionError("ZIP parsed before bounded directory check"),
            ):
                with self.assertRaises(UploadRejected):
                    self.validate(raw, limits)

    def test_compression_and_uncompressed_limits(self):
        for limits in (
            replace(DocxLimits(), max_member_bytes=100, max_xml_bytes=100),
            replace(DocxLimits(), max_total_bytes=100),
            replace(DocxLimits(), max_compressed_bytes=100),
            replace(DocxLimits(), max_ratio=1),
        ):
            with self.subTest(limits=limits), self.assertRaises(UploadRejected) as error:
                self.validate(archive(), limits)
            self.assertEqual(error.exception.code, "docx_limit")
        with self.assertRaises(UploadRejected):
            self.validate(archive(extra=[("word/media/bomb.bin", b"0" * 200000)]))

    def test_unsafe_names_duplicates_and_symlinks_are_rejected(self):
        for name in (
            "../outside.txt",
            "/absolute.txt",
            "word/../outside.txt",
            "word\\outside.txt",
            "C:outside.txt",
        ):
            with self.subTest(name=name), self.assertRaises(UploadRejected):
                self.validate(archive(extra=[(name, b"x")]))
        with self.assertRaises(UploadRejected):
            self.validate(archive(extra=[("WORD/DOCUMENT.XML", DOCUMENT)]))
        info = zipfile.ZipInfo("word/link")
        info.external_attr = 0o120777 << 16
        with self.assertRaises(UploadRejected):
            self.validate(archive(extra=[(info, b"../outside")]))

    def test_unsupported_compression_and_encryption_flags_are_rejected(self):
        with self.assertRaises(UploadRejected):
            self.validate(archive(compression=zipfile.ZIP_BZIP2))
        raw = bytearray(archive())
        for marker, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            pos = raw.find(marker)
            flags = struct.unpack_from("<H", raw, pos + offset)[0]
            struct.pack_into("<H", raw, pos + offset, flags | 1)
        with self.assertRaises(UploadRejected):
            self.validate(bytes(raw))

    def test_xml_dtd_entities_deep_nesting_and_node_budget(self):
        payloads = [
            b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>',
            (
                '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'
            ).encode("utf-16"),
            b"<broken>",
        ]
        for payload in payloads:
            with self.subTest(payload=payload[:15]), self.assertRaises(UploadRejected):
                self.validate(archive(extra=[("word/comments.xml", payload)]))
        with self.assertRaises(UploadRejected):
            self.validate(archive(), replace(DocxLimits(), max_xml_depth=2))
        with self.assertRaises(UploadRejected):
            self.validate(archive(), replace(DocxLimits(), max_xml_elements=2))

    def test_macro_content_and_external_main_relationship_are_rejected(self):
        macro = CONTENT_TYPES.replace(
            b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            b"application/vnd.ms-word.document.macroEnabled.main+xml",
        )
        with self.assertRaises(UploadRejected):
            self.validate(archive({"[Content_Types].xml": macro}))
        with self.assertRaises(UploadRejected):
            self.validate(archive(extra=[("word/vbaProject.bin", b"x")]))
        with self.assertRaises(UploadRejected):
            self.validate(
                archive(
                    {
                        "_rels/.rels": RELS.replace(
                            b'Target="word/document.xml"',
                            b'Target="https://example.com/doc.xml" TargetMode="External"',
                        )
                    }
                )
            )

    def test_crc_corruption_is_rejected(self):
        raw = bytearray(archive(compression=zipfile.ZIP_STORED))
        start = raw.find(b"Synthetic case.")
        raw[start] ^= 1
        with self.assertRaises(UploadRejected):
            self.validate(bytes(raw))

    def test_directory_entry_count_lies_and_multipart_are_rejected(self):
        for field, value in ((4, 1), (8, 1), (10, 65535)):
            raw = bytearray(archive())
            end = raw.rfind(b"PK\x05\x06")
            struct.pack_into("<H", raw, end + field, value)
            with self.subTest(field=field), self.assertRaises(UploadRejected):
                self.validate(bytes(raw))

    def test_corrupt_deflate_stream_is_a_validation_error(self):
        raw = bytearray(archive())
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info = z.getinfo("word/document.xml")
        offset = info.header_offset
        name_length, extra_length = struct.unpack_from("<HH", raw, offset + 26)
        payload = offset + 30 + name_length + extra_length
        raw[payload] |= 6
        with self.assertRaises(UploadRejected):
            self.validate(bytes(raw))

    def test_macro_default_content_type_is_rejected(self):
        types = CONTENT_TYPES.replace(
            b"</Types>",
            b'<Default Extension="bin" '
            b'ContentType="application/vnd.ms-office.vbaProject"/></Types>',
        )
        with self.assertRaises(UploadRejected):
            self.validate(
                archive({"[Content_Types].xml": types}, extra=[("word/hidden.bin", b"x")])
            )

    def test_explicit_internal_main_relationship_is_supported(self):
        rels = RELS.replace(
            b'Target="word/document.xml"', b'Target="word/document.xml" TargetMode="Internal"'
        )
        self.assertEqual(self.validate(archive({"_rels/.rels": rels})).entries, 3)

    def test_layers_keep_dependencies_pointing_inward(self):
        import ast

        root = Path(__file__).resolve().parents[1]
        # Inner layers may use pure standard-library modules and the legal_core domain package,
        # never frameworks, storage, HTTP or the outer src layers. datetime (domain) and
        # threading/concurrent.futures (application) stay pure stdlib: computation and
        # in-process orchestration only, no I/O.
        pure = {"dataclasses", "datetime", "enum", "hashlib", "re", "typing", "legal_core"}
        for layer, allowed in [
            ("domain", pure),
            (
                "application",
                pure
                | {
                    "collections",
                    "concurrent.futures",
                    "logging",
                    "threading",
                    "src.domain",
                    "src.application",
                },
            ),
        ]:
            for path in (root / "src" / layer).glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text())):
                    names = (
                        [node.module]
                        if isinstance(node, ast.ImportFrom)
                        else (
                            [item.name for item in node.names]
                            if isinstance(node, ast.Import)
                            else []
                        )
                    )
                    for name in names:
                        self.assertTrue(
                            any(
                                name == prefix or name.startswith(prefix + ".")
                                for prefix in allowed
                            ),
                            (path.name, name),
                        )

    def test_exact_limit_boundaries_are_accepted(self):
        raw = archive(compression=zipfile.ZIP_STORED)
        end = raw.rfind(b"PK\x05\x06")
        directory_bytes = struct.unpack_from("<I", raw, end + 12)[0]
        maximum = max(map(len, (CONTENT_TYPES, RELS, DOCUMENT)))
        limits = DocxLimits(
            max_compressed_bytes=len(raw),
            max_entries=3,
            max_directory_bytes=directory_bytes,
            max_total_bytes=len(CONTENT_TYPES + RELS + DOCUMENT),
            max_member_bytes=maximum,
            max_xml_bytes=maximum,
            max_ratio=1,
            max_xml_depth=5,
            max_xml_elements=9,
        )
        self.assertEqual(self.validate(raw, limits).entries, 3)

    def test_original_zip_names_with_nul_are_rejected(self):
        raw = archive({"word/document.xml": None}, extra=[("word/document.xmlX", DOCUMENT)])
        raw = raw.replace(b"word/document.xmlX", b"word/document.xml\x00")
        with self.assertRaises(UploadRejected):
            self.validate(raw)

    def test_invalid_limit_configuration_and_source_position(self):
        for value in (0, -1, True, "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DocxLimits(max_entries=value)
        source = io.BytesIO(archive())
        source.seek(5)
        ValidateUpload(DocxInspector(), DocxLimits()).execute(source, ".DOCX")
        self.assertEqual(source.tell(), 5)

    def test_declared_xml_under_binary_extension_cannot_bypass_xml_limits(self):
        styles_type = b"application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
        types = CONTENT_TYPES.replace(
            b"</Types>",
            b'<Override PartName="/word/styles.bin" ContentType="' + styles_type + b'"/></Types>',
        )
        relationship = (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="styles" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/styles" Target="styles.bin"/></Relationships>'
        )
        cases = [
            (
                b"<styles>" + b"<style/>" * 50 + b"</styles>",
                replace(DocxLimits(), max_xml_elements=24),
            ),
            (b"<x>" * 10 + b"</x>" * 10, replace(DocxLimits(), max_xml_depth=6)),
            (b"<styles>" + b" " * 2000 + b"</styles>", replace(DocxLimits(), max_xml_bytes=1024)),
            (b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>', DocxLimits()),
        ]
        for payload, limits in cases:
            with self.subTest(limits=limits), self.assertRaises(UploadRejected):
                self.validate(
                    archive(
                        {"[Content_Types].xml": types},
                        extra=[
                            ("word/_rels/document.xml.rels", relationship),
                            ("word/styles.bin", payload),
                        ],
                        compression=zipfile.ZIP_STORED,
                    ),
                    limits,
                )

    def test_valid_declared_xml_with_custom_extension_is_supported(self):
        types = CONTENT_TYPES.replace(
            b"</Types>", b'<Default Extension="svg" ContentType="image/svg+xml"/></Types>'
        )
        raw = archive(
            {"[Content_Types].xml": types},
            extra=[("word/media/image.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>')],
        )
        self.assertEqual(self.validate(raw).entries, 4)
