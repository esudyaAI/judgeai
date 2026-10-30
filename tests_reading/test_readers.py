import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.services.document_parser import extract_document
from tests_uploads.test_docx_guard import CONTENT_TYPES, DOCUMENT, RELS, archive


class ReadingFixture:
    def read(self, raw, suffix=".txt"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("synthetic" + suffix)
            path.write_bytes(raw)
            return asyncio.run(extract_document(path))


class DocumentReadingTests(ReadingFixture, unittest.TestCase):
    def test_utf_encodings_preserve_cyrillic_and_bom_is_not_content(self):
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32"):
            with self.subTest(encoding=encoding):
                result = self.read("Приговор суда".encode(encoding))
                self.assertEqual((result.text, result.status), ("Приговор суда", "ok"))

    def test_supported_legacy_cyrillic_is_not_silently_discarded(self):
        result = self.read("Приговор районного суда".encode("cp1251"))
        self.assertEqual(result.text, "Приговор районного суда")
        self.assertEqual(result.status, "ok")

    def test_binary_and_ambiguous_encoding_are_not_successful_text(self):
        for raw in (b"PK\x03\x04binary", b"ab\x00cd", b"\xff", b"hello\xc3", b"\xff\xfe\x00"):
            with self.subTest(raw=raw):
                result = self.read(raw)
                self.assertEqual((result.text, result.status), ("", "error"))

    def test_word_tables_and_paragraphs_follow_document_order(self):
        body = (
            b"<w:p><w:r><w:t>Before</w:t></w:r></w:p>"
            b"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table evidence</w:t></w:r></w:p>"
            b"</w:tc></w:tr></w:tbl><w:p><w:r><w:t>After</w:t></w:r></w:p>"
        )
        raw = archive(
            {
                "word/document.xml": DOCUMENT[: DOCUMENT.index(b"<w:body>")]
                + b"<w:body>"
                + body
                + b"</w:body></w:document>"
            }
        )
        result = self.read(raw, ".docx")
        self.assertEqual(result.text.splitlines(), ["Before", "Table evidence", "After"])
        self.assertEqual(result.status, "ok")

    def test_dotx_and_strict_word_are_readable(self):
        template = CONTENT_TYPES.replace(
            b"wordprocessingml.document.main+xml", b"wordprocessingml.template.main+xml"
        )
        strict_doc = DOCUMENT.replace(
            b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
            b"http://purl.oclc.org/ooxml/wordprocessingml/main",
        )
        strict_rels = RELS.replace(
            b"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            b"http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument",
        )
        for raw, suffix in [
            (archive({"[Content_Types].xml": template}), ".dotx"),
            (archive({"word/document.xml": strict_doc, "_rels/.rels": strict_rels}), ".docx"),
        ]:
            with self.subTest(suffix=suffix):
                result = self.read(raw, suffix)
                self.assertEqual((result.text, result.status), ("Synthetic case.", "ok"))

    def test_word_notes_are_included_and_unreadable_objects_are_explicit(self):
        note = (
            b'<w:footnotes xmlns:w="http://schemas.openxmlformats.org/'
            b'wordprocessingml/2006/main"><w:footnote w:id="1"><w:p><w:r>'
            b"<w:t>Important note</w:t></w:r></w:p></w:footnote></w:footnotes>"
        )
        document = DOCUMENT.replace(
            b"</w:body>",
            b'<w:p><w:r><w:drawing/><w:footnoteReference w:id="1"/></w:r></w:p></w:body>',
        )
        result = self.read(
            archive(
                {
                    "word/document.xml": document,
                    "word/footnotes.xml": note,
                    "word/_rels/document.xml.rels": (
                        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        b'<Relationship Id="n1" Type="http://schemas.openxmlformats.org/'
                        b'officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
                        b"</Relationships>"
                    ),
                }
            ),
            ".docx",
        )
        self.assertIn("Important note", result.text)
        self.assertEqual(result.status, "partial")
        self.assertIn("unsupported_content", result.issues)

    def test_legacy_word_is_explicitly_unsupported(self):
        for suffix in (".doc", ".dot", ".rtf", ".docm", ".dotm"):
            result = self.read(b"synthetic legacy content", suffix)
            self.assertEqual(result.status, "unsupported")
            self.assertIn("unsupported_format", result.issues)

    def test_image_only_pdf_explains_missing_text_layer(self):
        from tests_pdf.fixtures import image_pdf

        result = self.read(image_pdf(), ".pdf")
        self.assertEqual(result.status, "empty")
        self.assertEqual(result.unread_pages, (1,))
        self.assertIn("no_text_layer", result.issues)


class ReadingLimitsTests(ReadingFixture, unittest.TestCase):
    def test_text_byte_character_and_word_output_limits_fail_explicitly(self):
        for setting, raw, suffix in [
            ("MAX_TEXT_BYTES", b"12345678901", ".txt"),
            ("MAX_TEXT_CHARACTERS", b"12345678901", ".txt"),
            ("MAX_TEXT_CHARACTERS", archive(), ".docx"),
        ]:
            with (
                self.subTest(setting=setting, suffix=suffix),
                patch(
                    (
                        "src.infrastructure.word_reader."
                        if suffix == ".docx"
                        else "src.infrastructure.document_readers."
                    )
                    + setting,
                    10,
                ),
            ):
                document = self.read(raw, suffix)
                self.assertEqual((document.text, document.status), ("", "error"))
                self.assertIn("resource_limit", document.issues)

    def test_big_endian_unicode_is_supported(self):
        for encoding, bom in [("utf-16-be", b"\xfe\xff"), ("utf-32-be", b"\x00\x00\xfe\xff")]:
            self.assertEqual(
                self.read(bom + "Приговор суда".encode(encoding)).text, "Приговор суда"
            )

    def test_pdf_versions_compression_and_xref_stream_text(self):
        from tests_pdf.fixtures import pdf, xref_stream_pdf

        variants = [
            pdf(),
            pdf(compressed=True),
            xref_stream_pdf(),
            pdf().replace(b"%PDF-1.7", b"%PDF-2.0"),
        ]
        for raw in variants:
            with self.subTest(header=raw[:8]):
                result = self.read(raw, ".pdf")
                self.assertEqual(result.text, "Synthetic judgment.")
                self.assertEqual(result.status, "ok")

    def test_tracked_changes_are_not_silently_presented_as_finalized_text(self):
        document = DOCUMENT.replace(
            b"</w:body>",
            b"<w:del><w:p><w:r><w:delText>Deleted allegation</w:delText>"
            b"</w:r></w:p></w:del></w:body>",
        )
        result = self.read(archive({"word/document.xml": document}), ".docx")
        self.assertNotIn("Deleted allegation", result.text)
        self.assertEqual(result.status, "partial")
        self.assertIn("tracked_changes", result.issues)


class ReadingReviewRegressions(ReadingFixture, unittest.TestCase):
    def test_utf8_bom_forbids_legacy_fallback_and_truncated_unicode_is_not_reinterpreted(self):
        for raw in [
            b"\xef\xbb\xbf" + "Приговор районного суда".encode("cp1251"),
            ("а" * 32).encode()[:-1],
        ]:
            result = self.read(raw)
            self.assertEqual((result.text, result.status), ("", "error"))
            self.assertIn("invalid_encoding", result.issues)

    def test_mutually_exclusive_word_alternatives_are_never_combined(self):
        alternatives = (
            b'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/marku'
            b'p-compatibility/2006"><mc:Choice Requires="x"><w:p><w:r><w:t>GUILTY</w'
            b":t></w:r></w:p></mc:Choice><mc:Fallback><w:p><w:r><w:t>NOT GUILTY</w:t"
            b"></w:r></w:p></mc:Fallback></mc:AlternateContent>"
        )
        document = DOCUMENT.replace(b"</w:body>", alternatives + b"</w:body>")
        result = self.read(archive({"word/document.xml": document}), ".docx")
        self.assertNotIn("GUILTY", result.text)
        self.assertEqual(result.status, "partial")
        self.assertIn("unsupported_content", result.issues)

    def test_orphan_word_parts_are_not_current_content(self):
        header = (
            b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/200'
            b'6/main"><w:p><w:r><w:t>Old removed allegation</w:t></w:r></w:p></w:hdr'
            b">"
        )
        result = self.read(archive({"word/header99.xml": header}), ".docx")
        self.assertEqual((result.text, result.status), ("Synthetic case.", "ok"))

    def test_referenced_header_can_have_a_nonstandard_part_name(self):
        header = (
            b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/200'
            b'6/main"><w:p><w:r><w:t>Current header</w:t></w:r></w:p></w:hdr>'
        )
        document = DOCUMENT.replace(
            b"<w:body>",
            b'<w:body xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        ).replace(b"</w:body>", b'<w:sectPr><w:headerReference r:id="h1"/></w:sectPr></w:body>')
        rels = (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/r'
            b'elationships"><Relationship Id="h1" Type="http://schemas.openxmlformat'
            b's.org/officeDocument/2006/relationships/header" Target="../custom/curr'
            b'ent.xml"/></Relationships>'
        )
        result = self.read(
            archive(
                {
                    "word/document.xml": document,
                    "word/_rels/document.xml.rels": rels,
                    "custom/current.xml": header,
                }
            ),
            ".docx",
        )
        self.assertIn("Current header", result.text)
        self.assertEqual(result.status, "ok")

    def test_removed_section_properties_do_not_reactivate_old_headers(self):
        header = (
            b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:p><w:r><w:t>Removed header</w:t></w:r></w:p></w:hdr>"
        )
        document = DOCUMENT.replace(
            b"<w:body>",
            b'<w:body xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        ).replace(
            b"</w:body>",
            b'<w:sectPr><w:sectPrChange><w:sectPr><w:headerReference r:id="old"/>'
            b"</w:sectPr></w:sectPrChange></w:sectPr></w:body>",
        )
        rels = (
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="old" Type="http://schemas.openxmlformats.org/'
            b'officeDocument/2006/relationships/header" Target="old.xml"/></Relationships>'
        )
        result = self.read(
            archive(
                {
                    "word/document.xml": document,
                    "word/_rels/document.xml.rels": rels,
                    "word/old.xml": header,
                }
            ),
            ".docx",
        )
        self.assertNotIn("Removed header", result.text)
        self.assertEqual(result.status, "partial")
        self.assertIn("tracked_changes", result.issues)


class WordPageCountTests(ReadingFixture, unittest.TestCase):
    APP_XML = (
        b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        b'extended-properties"><Pages>7</Pages><Words>900</Words></Properties>'
    )

    def test_word_page_count_comes_from_saved_editor_metadata(self):
        result = self.read(archive({"docProps/app.xml": self.APP_XML}), ".docx")
        self.assertEqual(result.page_count, 7)
        self.assertEqual((result.text, result.status), ("Synthetic case.", "ok"))

    def test_word_without_metadata_has_unknown_page_count(self):
        result = self.read(archive(), ".docx")
        self.assertIsNone(result.page_count)
        self.assertEqual(result.status, "ok")

    def test_broken_or_meaningless_metadata_never_breaks_reading(self):
        for payload in (
            b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'extended-properties"><Pages>0</Pages></Properties>',
            b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'extended-properties"><Pages>many</Pages></Properties>',
            b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'extended-properties"><Words>900</Words></Properties>',
        ):
            with self.subTest(payload=payload[:20]):
                result = self.read(archive({"docProps/app.xml": payload}), ".docx")
                self.assertIsNone(result.page_count)
                self.assertEqual((result.text, result.status), ("Synthetic case.", "ok"))

    def test_malformed_metadata_xml_is_rejected_with_the_package(self):
        # The DOCX inspector parses every package part at admission: malformed XML
        # anywhere is rejected before the reader runs (unchanged behavior).
        result = self.read(archive({"docProps/app.xml": b"<not-xml"}), ".docx")
        self.assertEqual((result.text, result.status), ("", "error"))

    def test_plain_text_has_no_page_count(self):
        result = self.read("Приговор суда".encode())
        self.assertIsNone(result.page_count)
