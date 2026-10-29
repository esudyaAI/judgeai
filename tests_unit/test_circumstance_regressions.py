"""Synthetic counterexamples; corpus coverage must be measured separately."""

import unittest

from legal_core.precedents import Recidivism

from src.infrastructure.circumstance_extractor import extract_circumstances


class CircumstanceRegressionTests(unittest.TestCase):
    def test_unrelated_negative_clause_does_not_erase_children(self):
        reading = extract_circumstances(
            "Смягчающими обстоятельствами суд признаёт наличие малолетнего ребенка; "
            "отягчающих обстоятельств не установлено."
        )
        self.assertIn("61.1.г", reading.mitigating)
        self.assertFalse(reading.aggravating)

    def test_sentence_subject_before_marker_is_not_lost(self):
        reading = extract_circumstances(
            "Наличие малолетних детей суд признаёт обстоятельством, смягчающим наказание."
        )
        self.assertIn("61.1.г", reading.mitigating)

    def test_listed_circumstances_continue_after_colon_and_newlines(self):
        reading = extract_circumstances(
            "Суд признаёт смягчающими обстоятельствами:\n"
            "- наличие малолетнего ребёнка;\n- явку с повинной;\n"
            "- добровольное возмещение ущерба."
        )
        self.assertEqual(set(reading.mitigating), {"61.1.г", "61.1.и", "61.1.к"})

    def test_opposite_clauses_do_not_share_facts(self):
        reading = extract_circumstances(
            "Смягчающими признаются наличие малолетнего ребёнка, "
            "а отягчающим — совершение преступления группой лиц."
        )
        self.assertEqual(set(reading.mitigating), {"61.1.г"})
        self.assertEqual(set(reading.aggravating), {"63.1.в"})

    def test_denied_child_is_not_a_positive_match(self):
        reading = extract_circumstances(
            "Суд не признаёт наличие малолетнего ребёнка смягчающим обстоятельством."
        )
        self.assertNotIn("61.1.г", reading.mitigating)

    def test_one_rejected_fact_does_not_erase_the_accepted_other_fact(self):
        reading = extract_circumstances(
            "Явку с повинной суд признаёт смягчающим обстоятельством, "
            "а наличие малолетнего ребёнка не признаёт смягчающим обстоятельством."
        )
        self.assertIn("61.1.и", reading.mitigating)
        self.assertNotIn("61.1.г", reading.mitigating)

    def test_minors_are_not_automatically_young_children(self):
        reading = extract_circumstances("Смягчающим признано наличие несовершеннолетнего ребёнка.")
        self.assertNotIn("61.1.г", reading.mitigating)

    def test_not_previously_convicted_spelling_variants(self):
        for text in ["несудимый", "не судимая", "ранее не судимого", "судимости не имеет"]:
            with self.subTest(text=text):
                reading = extract_circumstances("", introduction=f"Подсудимый, {text}.")
                self.assertIs(reading.recidivism, Recidivism.NONE)

    def test_explicit_no_recidivism_is_recognized_without_requiring_no_convictions(self):
        reading = extract_circumstances("Рецидив преступлений в действиях подсудимого отсутствует.")
        self.assertIs(reading.recidivism, Recidivism.NONE)

    def test_several_recidivism_degrees_are_not_order_dependent(self):
        reading = extract_circumstances(
            "Суд установил рецидив преступлений. Указанный рецидив является опасным."
        )
        self.assertIs(reading.recidivism, Recidivism.DANGEROUS)

    def test_unapplied_rule_does_not_erase_applied_rule_in_other_clause(self):
        reading = extract_circumstances(
            "Суд применяет ч. 1 ст. 62 УК РФ, но оснований для применения "
            "ст. 64 УК РФ не усматривает."
        )
        self.assertIn("62.1", reading.applied_general)
        self.assertNotIn("64", reading.applied_general)

    def test_explicit_code_accepts_straight_quotes_and_unquoted_point(self):
        for reference in ['п. "г" ч. 1 ст. 61', "п. г ч. 1 ст. 61"]:
            with self.subTest(reference=reference):
                reading = extract_circumstances(
                    f"Смягчающее обстоятельство предусмотрено {reference} УК РФ."
                )
                self.assertIn("61.1.г", reading.mitigating)

    def test_appeal_claim_is_not_automatically_a_court_finding(self):
        reading = extract_circumstances(
            "Защитник просит признать наличие малолетнего ребёнка смягчающим обстоятельством."
        )
        self.assertNotIn("61.1.г", reading.mitigating)

    def test_explicit_recidivism_does_not_form_wording(self):
        reading = extract_circumstances("Судимости рецидив преступлений не образуют.")
        self.assertIs(reading.recidivism, Recidivism.NONE)

    def test_negation_of_a_degree_is_not_absence_of_all_recidivism(self):
        reading = extract_circumstances("Опасный рецидив в действиях подсудимого отсутствует.")
        self.assertIsNone(reading.recidivism)

    def test_also_does_not_start_an_opposing_clause(self):
        reading = extract_circumstances(
            "Суд признал смягчающими явку с повинной, а также признание вины."
        )
        self.assertEqual(set(reading.mitigating), {"61.1.и", "61.2"})

    def test_party_request_list_never_becomes_a_court_finding(self):
        reading = extract_circumstances(
            "Защитник просит признать смягчающими обстоятельствами: состояние здоровья; "
            "наличие малолетнего ребёнка; явку с повинной."
        )
        self.assertEqual(reading.mitigating, {})

    def test_denied_recidivism_degree_does_not_become_a_positive_degree(self):
        for text in [
            "Рецидив преступлений не является опасным.",
            "Рецидив преступлений не признан особо опасным.",
        ]:
            with self.subTest(text=text):
                reading = extract_circumstances(text)
                self.assertIs(reading.recidivism, Recidivism.SIMPLE)
