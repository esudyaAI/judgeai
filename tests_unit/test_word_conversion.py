"""Executed inside the offline preview image, using real LibreOffice and synthetic OOXML."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.preview_spool import PreviewSpool
from src.infrastructure.word_preview_worker import run_one


def document():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override
 PartName="/word/document.xml"
 ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
 Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p>
<w:r>
<w:rPr>
<w:b/>
</w:rPr>
<w:t>First page heading</w:t>
</w:r>
</w:p>
<w:tbl>
<w:tblPr>
<w:tblW w:w="6000" w:type="dxa"/>
</w:tblPr>
<w:tblGrid>
<w:gridCol w:w="3000"/>
<w:gridCol w:w="3000"/>
</w:tblGrid>
<w:tr>
<w:tc>
<w:p>
<w:r>
<w:t>Table left</w:t>
</w:r>
</w:p>
</w:tc>
<w:tc>
<w:p>
<w:r>
<w:t>Table right</w:t>
</w:r>
</w:p>
</w:tc>
</w:tr>
</w:tbl>
<w:p>
<w:r>
<w:br w:type="page"/>
</w:r>
<w:r>
<w:t>Second page marker</w:t>
</w:r>
</w:p>
<w:sectPr>
<w:pgSz w:w="11906" w:h="16838"/>
</w:sectPr>
</w:body>
</w:document>""",
        )
    return output.getvalue()


class WorkerPolicyTests(unittest.TestCase):
    def test_failed_conversion_removes_source_and_hides_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.docx"
            source.write_bytes(b"synthetic")
            spool = PreviewSpool(root / "jobs")
            job = spool.create(source, "case.docx", 4, None)
            with patch(
                "src.infrastructure.word_preview_worker.convert",
                side_effect=RuntimeError("private details"),
            ):
                self.assertTrue(run_one(spool))
            result = spool.get(job["id"], 4)
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("private details", result["error"])
            self.assertFalse((spool.root / job["id"] / "source.docx").exists())
            self.assertFalse(run_one(spool))


if __name__ == "__main__":
    # Real conversion is mandatory for this container acceptance command. It is kept
    # outside ordinary unit discovery because macOS/non-root hosts are not the worker.
    import pdfplumber

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "input.docx"
        source.write_bytes(document())
        spool = PreviewSpool(root / "jobs")
        job = spool.create(source, "Synthetic two pages.docx", 7, None)
        assert run_one(spool)
        result = spool.get(job["id"], 7)
        assert result["status"] == "ready", result
        with pdfplumber.open(spool.pdf(job["id"], 7)) as pdf:
            assert len(pdf.pages) == 2, len(pdf.pages)
            first = pdf.pages[0].extract_text()
            second = pdf.pages[1].extract_text()
            assert "First page heading" in first
            assert "Table left" in first and "Table right" in first
            assert "Second page marker" in second
            assert any("Bold" in char["fontname"] for char in pdf.pages[0].chars)
            assert abs(float(pdf.pages[0].width) - 595) < 2
        assert not (spool.root / job["id"] / "source.docx").exists()
        print(
            "PASS: two PDF pages, page break, A4 geometry, bold heading, table text, source cleanup"
        )
