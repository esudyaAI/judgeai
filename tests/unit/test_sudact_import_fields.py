"""Pure mapping of crawl records into knowledge_verdicts constructor fields."""

import unittest

from src.services.sudact_import import SUDACT_SOURCE_TYPE, record_fields

RECORD = {
    "url": "https://sudact.ru/regular/doc/abc/",
    "fetched_at": "2026-10-28T10:00:00+00:00",
    "html_sha256": "h" * 64,
    "title": "Приговор № 1-120/2026 от 14 апреля 2026 г.",
    "act_kind": "приговор",
    "category": None,
    "case_number": "1-120/2026",
    "uid": "21RS0022-01-2026-000904-27",
    "court_name": "Новочебоксарский городской суд",
    "region": "Чувашская Республика",
    "decision_date": "2026-04-14",
    "text": "ПРИГОВОР УСТАНОВИЛ ПРИГОВОРИЛ",
    "text_sha256": "t" * 64,
    "articles": ["158"],
    "raw_path": "/data/sudact/raw/abc.html",
}


class RecordFieldsTests(unittest.TestCase):
    def test_fields_map_to_model(self):
        fields = record_fields(RECORD)
        self.assertEqual(fields["uid"], "21RS0022-01-2026-000904-27")
        self.assertEqual(fields["case_number"], "1-120/2026")
        self.assertEqual(fields["court_name"], "Новочебоксарский городской суд")
        self.assertEqual(str(fields["verdict_date"]), "2026-04-14")
        self.assertEqual(fields["source_type"], SUDACT_SOURCE_TYPE)
        self.assertEqual(fields["source_filename"], "abc")
        self.assertEqual(fields["file_hash"], "t" * 64)
        self.assertEqual(fields["raw_text"], "ПРИГОВОР УСТАНОВИЛ ПРИГОВОРИЛ")
        self.assertEqual(fields["status"], "indexed")

    def test_provenance_in_structured(self):
        structured = record_fields(RECORD)["structured"]
        self.assertEqual(structured["source_url"], RECORD["url"])
        self.assertEqual(structured["fetched_at"], RECORD["fetched_at"])
        self.assertEqual(structured["raw_path"], RECORD["raw_path"])
        self.assertEqual(structured["title"], RECORD["title"])
        self.assertEqual(structured["region"], RECORD["region"])
        self.assertIsNone(structured.get("category"))

    def test_bad_date_and_empty_text(self):
        broken = dict(RECORD, decision_date="не дата", text="  ")
        fields = record_fields(broken)
        self.assertIsNone(fields["verdict_date"])
        self.assertEqual(fields["status"], "empty")

    def test_missing_url_falls_back_to_filename(self):
        fields = record_fields({"text": "x", "text_sha256": "t" * 64})
        self.assertEqual(fields["source_filename"], "sudact")
        self.assertEqual(fields["structured"], {})


if __name__ == "__main__":
    unittest.main()
