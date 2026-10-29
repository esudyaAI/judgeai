import unittest

from legal_core.precedents import Qualification, parse_qualifications

from src.application.precedent_cards import build_card
from src.infrastructure.verdict_reader import RegexVerdictReader
from src.services.qualification_reference import parse_qualification_reference


class QualificationCitationTests(unittest.TestCase):
    def test_procedural_appeal_references_do_not_erase_criminal_qualification(self):
        text = "Осудить по ч. 1 ст. 158 УК РФ. Обжалование в порядке ст. 389.1 УПК РФ."
        self.assertEqual(parse_qualifications(text), (Qualification("158", 1),))

    def test_criminal_citations_are_not_mixed_with_procedural_articles(self):
        text = "Разъяснены ст. 307, 308 УПК РФ. Осудить по ст. 158 ч. 2 УК РФ."
        self.assertEqual(parse_qualifications(text), (Qualification("158", 2),))

    def test_capitalization_and_point_quotes(self):
        for text in ['П. "В" Ч. 2 СТ. 158 УК РФ', "п. в ч.2 ст.158 УК РФ"]:
            with self.subTest(text=text):
                self.assertEqual(parse_qualifications(text), (Qualification("158", 2, "в"),))

    def test_part_after_article_survives_the_punishment_reader(self):
        text = (
            "УСТАНОВИЛ:\nКража.\nПРИГОВОРИЛ:\nПризнать виновным по ст. 158 ч. 2 УК РФ "
            "и назначить наказание в виде лишения свободы на срок 2 года."
        )
        card = build_card(RegexVerdictReader(), text).card
        self.assertEqual(card.main_qualification, Qualification("158", 2))
        self.assertEqual(card.imprisonment_months, 24)

    def test_statute_reference_uses_the_same_citation_parser(self):
        reference = parse_qualification_reference("Ст. 158 ч. 2 УК РФ. Ст. 389.1 УПК РФ.")
        self.assertIsNotNone(reference)
        self.assertEqual((reference.article, reference.part), ("158", 2))

    def test_code_applies_to_grouped_procedural_references(self):
        self.assertEqual(parse_qualifications("ст. 307 и ст. 308 УПК РФ"), ())

    def test_procedural_article_ranges_do_not_become_criminal_qualifications(self):
        for separator in ["-", "–", "—"]:
            text = f"Разъяснены ст. 307 {separator} 309 УПК РФ. Осудить по ч. 1 ст. 158 УК РФ."
            with self.subTest(separator=separator):
                self.assertEqual(parse_qualifications(text), (Qualification("158", 1),))
                reference = parse_qualification_reference(text)
                self.assertEqual(reference.article, "158")
