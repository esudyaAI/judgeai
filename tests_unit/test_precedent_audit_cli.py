import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path

from src.cli.precedent_audit import main, read_sources

TEXT = "УСТАНОВИЛ:\nКража.\nПРИГОВОРИЛ:\nОсудить по ч. 1 ст. 158 УК РФ."


class AuditCliTests(unittest.TestCase):
    def test_all_lines_counted_including_bad_records_and_private_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cases.jsonl"
            source.write_text(
                json.dumps({"id": 1, "text": TEXT})
                + "\nnot json\n"
                + json.dumps({"id": 3, "text": TEXT, "source_type": "chat"})
                + "\n"
                + json.dumps({"id": 4, "text": []})
                + "\n",
                encoding="utf-8",
            )
            rows = read_sources(source)
            self.assertEqual(len(rows), 4)
            output = Path(directory) / "report.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(main(["--file", str(source), "--out", str(output)]), 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["summary"]["sources"], 4)
            self.assertEqual(report["summary"]["errors"], 2)
            self.assertEqual(report["summary"]["skipped_private"], 1)
            self.assertNotIn("Кража", stdout.getvalue())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_previous_audit_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.jsonl", Path(directory) / "audit.json"
            source.write_text(json.dumps({"text": TEXT}) + "\n")
            output.write_text("keep prior audit")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--file", str(source), "--out", str(output)])
            self.assertEqual(output.read_text(), "keep prior audit")

    def test_quotes_stay_out_of_default_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.jsonl", Path(directory) / "audit.json"
            source.write_text(json.dumps({"text": TEXT}) + "\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--file", str(source), "--out", str(output)]), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["summary"]["read"], 1)
            self.assertTrue(
                all(
                    not f["quote"]
                    for d in report["documents"]
                    for c in d["cards"]
                    for f in c["fields"]
                )
            )
