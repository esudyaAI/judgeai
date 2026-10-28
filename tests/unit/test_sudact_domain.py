"""Domain rules of the sudact crawler: classification, identity, dedup keys."""

import unittest

from src.domain.sudact import (
    SudactDocument,
    extract_articles,
    extract_case_number,
    extract_decision_date,
    extract_uid,
    normalize_act_kind,
    split_court,
)


def _doc(**kwargs) -> SudactDocument:
    base = dict(
        url="https://sudact.ru/regular/doc/abc/",
        fetched_at="2026-10-28T00:00:00+00:00",
        html_sha256="h" * 64,
        title="Приговор № 1-1/2026 от 1 января 2026 г.",
        act_kind="приговор",
        text="текст",
        text_sha256="t" * 64,
    )
    base.update(kwargs)
    return SudactDocument(**base)


class ActKindTests(unittest.TestCase):
    def test_first_instance_verdict_is_recognized(self):
        self.assertEqual(
            normalize_act_kind("Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026"),
            "приговор",
        )
        self.assertEqual(
            normalize_act_kind("Апелляционное определение № 22-111/2026"),
            "апелляционное определение",
        )
        self.assertEqual(normalize_act_kind("Решение № 2-902/2026 от 22 апреля 2026 г."), "решение")

    def test_unknown_or_empty_titles(self):
        self.assertIsNone(normalize_act_kind(""))
        self.assertIsNone(normalize_act_kind(":: СудАкт.ру"))
        self.assertIsNone(normalize_act_kind("Какой-то заголовок без номера"))


class IdentityTests(unittest.TestCase):
    def test_case_number_from_title(self):
        self.assertEqual(
            extract_case_number("Приговор № 01-0362/2026 1-698/2023 от 16 апреля"),
            "01-0362/2026",
        )
        self.assertIsNone(extract_case_number("Приговор без номера"))

    def test_uid_from_text_with_and_without_number_sign(self):
        self.assertEqual(
            extract_uid("Дело № 1-120/2026 УИД 21RS0022-01-2026-000904-27 ПРИГОВОР"),
            "21RS0022-01-2026-000904-27",
        )
        self.assertEqual(
            extract_uid("УИД №18RS0002-01-2026-001481-13"),
            "18RS0002-01-2026-001481-13",
        )
        self.assertIsNone(extract_uid("без идентификатора"))
        self.assertIsNone(extract_uid("УИД 21RS0022"))

    def test_decision_date_from_title(self):
        self.assertEqual(str(extract_decision_date("от 14 апреля 2026 г.")), "2026-04-14")
        self.assertIsNone(extract_decision_date("от 14 апрелия 2026 г."))
        self.assertIsNone(extract_decision_date("нет даты"))
        self.assertIsNone(extract_decision_date("от 31 февраля 2026 г."))

    def test_articles_unique_in_order(self):
        text = "ст. 158 УК, повторно ст. 158, ст. 159.3, ст. 61"
        self.assertEqual(extract_articles(text), ["158", "159.3", "61"])

    def test_court_and_region_split(self):
        court, region = split_court("Новочебоксарский городской суд (Чувашская Республика )")
        self.assertEqual(court, "Новочебоксарский городской суд")
        self.assertEqual(region, "Чувашская Республика")
        self.assertEqual(
            split_court("Московский областной суд"), ("Московский областной суд", None)
        )
        self.assertEqual(split_court(""), (None, None))


class DedupKeyTests(unittest.TestCase):
    def test_uid_wins_over_hash(self):
        doc = _doc(uid="21RS0022-01-2026-000904-27")
        self.assertEqual(doc.dedup_key, "uid:21RS0022-01-2026-000904-27")
        self.assertTrue(doc.is_verdict)

    def test_hash_used_without_uid(self):
        doc = _doc(uid=None)
        self.assertEqual(doc.dedup_key, f"sha:{doc.text_sha256}")
        self.assertFalse(_doc(act_kind="решение").is_verdict)

    def test_record_round_trip_keeps_fields(self):
        record = _doc().to_record()
        self.assertEqual(record["act_kind"], "приговор")
        self.assertEqual(record["url"], "https://sudact.ru/regular/doc/abc/")


if __name__ == "__main__":
    unittest.main()
