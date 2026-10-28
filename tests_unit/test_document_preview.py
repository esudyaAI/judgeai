import tempfile
import unittest
from pathlib import Path

from src.application.document_preview import PreviewNotFound, PreviewUnavailable
from src.infrastructure.preview_spool import PreviewSpool


class PreviewSpoolTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / "source.docx"
        self.source.write_bytes(b"synthetic validated source")
        self.spool = PreviewSpool(self.root / "jobs", ttl=600, capacity=2)

    def test_owner_scope_binding_and_private_modes(self):
        job = self.spool.create(self.source, "case.docx", 4, (9, 12))
        self.assertEqual(job["status"], "queued")
        self.assertEqual(self.spool.get(job["id"], 4)["attachment"], [9, 12])
        with self.assertRaises(PreviewNotFound):
            self.spool.get(job["id"], 5)
        with self.assertRaises(PreviewNotFound):
            self.spool.get("../source.docx", 4)
        self.assertEqual((self.spool.root / job["id"]).stat().st_mode & 0o777, 0o700)

    def test_atomic_capacity_and_expiry_cleanup(self):
        first = self.spool.create(self.source, "a.docx", 4, None)
        self.spool.create(self.source, "b.docx", 5, None)
        with self.assertRaises(PreviewUnavailable):
            self.spool.create(self.source, "c.docx", 6, None)
        self.spool.cleanup(now=first["created_at"] + 601)
        self.assertFalse((self.spool.root / first["id"]).exists())
        with self.assertRaises(PreviewNotFound):
            self.spool.get(first["id"], 4)

    def test_converter_output_symlink_is_rejected(self):
        job = self.spool.create(self.source, "a.docx", 4, None)
        (self.spool.root / job["id"] / "preview.pdf").symlink_to(self.source)
        with self.assertRaises(PreviewNotFound):
            self.spool.pdf(job["id"], 4)
