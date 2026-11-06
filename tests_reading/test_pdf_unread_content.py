"""T17.4: PDF content the reader does not read (attachments, portfolios, XFA) is reported."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from src.services.document_parser import extract_document
from tests_pdf.fixtures import package, stream

TEXT = b"BT /F1 12 Tf 72 720 Td (Synthetic judgment.) Tj ET"
FILESPEC = b"<< /Type /Filespec /F (note.txt) /EF << /F 8 0 R >> >>"
EMBEDDED = stream(b"hidden synthetic note", attrs=b"/Type /EmbeddedFile")


def text_pdf(catalog=b"", page=b"", extra=(), content=TEXT):
    """One page; objects 6+ are `extra`, so references from `catalog`/`page` stay stable."""
    return package(
        [
            b"<< /Type /Catalog /Pages 2 0 R " + catalog + b">>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> " + page + b">>",
            stream(content),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            *extra,
        ]
    )


ATTACHMENT = text_pdf(
    b"/Names << /EmbeddedFiles 6 0 R >>",
    extra=(b"<< /Names [(note.txt) 7 0 R] >>", FILESPEC, EMBEDDED),
)


class PdfUnreadContentTests(unittest.TestCase):
    def read(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pdf"
            path.write_bytes(raw)
            return asyncio.run(extract_document(path))

    def test_plain_pdf_and_empty_containers_stay_complete(self):
        for raw in (
            text_pdf(),
            text_pdf(b"/Names << /EmbeddedFiles << /Names [] >> >>"),
            text_pdf(b"/AcroForm << /Fields [] >>"),
            text_pdf(
                page=b"/Annots [6 0 R]",
                extra=(b"<< /Type /Annot /Subtype /Text /Rect [0 0 10 10] >>",),
            ),
        ):
            with self.subTest(raw=raw[-120:]):
                result = self.read(raw)
                self.assertEqual((result.status, result.issues), ("ok", ()))
                self.assertIn("Synthetic judgment.", result.text)

    def test_embedded_files_make_the_reading_partial(self):
        result = self.read(ATTACHMENT)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.issues, ("pdf_attachments",))
        self.assertIn("Synthetic judgment.", result.text)
        self.assertNotIn("hidden synthetic note", result.text)

    def test_nested_name_tree_with_kids_counts_as_attachments(self):
        raw = text_pdf(
            b"/Names << /EmbeddedFiles 6 0 R >>",
            extra=(
                b"<< /Kids [9 0 R] >>",
                FILESPEC,
                EMBEDDED,
                b"<< /Limits [(note.txt) (note.txt)] /Names [(note.txt) 7 0 R] >>",
            ),
        )
        self.assertEqual(self.read(raw).issues, ("pdf_attachments",))

    def test_file_attachment_annotation_is_reported(self):
        raw = text_pdf(
            page=b"/Annots [6 0 R]",
            extra=(
                b"<< /Type /Annot /Subtype /FileAttachment /Rect [0 0 10 10] /FS 7 0 R >>",
                FILESPEC,
                EMBEDDED,
            ),
        )
        result = self.read(raw)
        self.assertEqual((result.status, result.issues), ("partial", ("pdf_attachments",)))

    def test_portfolio_reports_only_the_cover_was_read(self):
        raw = text_pdf(
            b"/Names << /EmbeddedFiles 6 0 R >> /Collection << /Type /Collection >>",
            extra=(b"<< /Names [(note.txt) 7 0 R] >>", FILESPEC, EMBEDDED),
        )
        result = self.read(raw)
        self.assertEqual((result.status, result.issues), ("partial", ("pdf_portfolio",)))

    def test_portfolio_with_an_empty_cover_stays_empty(self):
        raw = text_pdf(b"/Collection << /Type /Collection >>", content=b"q Q")
        result = self.read(raw)
        self.assertEqual(result.status, "empty")
        self.assertEqual(result.issues, ("no_text_layer", "pdf_portfolio"))
        self.assertEqual(result.unread_pages, (1,))

    def test_xfa_form_is_reported(self):
        raw = text_pdf(b"/AcroForm << /Fields [] /XFA 6 0 R >>", extra=(stream(b"<xdp:xdp/>"),))
        result = self.read(raw)
        self.assertEqual((result.status, result.issues), ("partial", ("xfa_form",)))


if __name__ == "__main__":
    unittest.main()
