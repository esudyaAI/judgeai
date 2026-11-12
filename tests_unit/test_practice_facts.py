"""T45.1 — factual practice questions answered by code: no DB, HTTP, framework or model."""

import unittest
from datetime import date

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification

from src.domain.practice_facts import (
    PracticeTermQuestion,
    PracticeVerdict,
    covers,
    describe_practice_term_facts,
    parse_practice_term_question,
    practice_term_facts,
)


def months(n):
    return PunishmentTerm(PunishmentKind.IMPRISONMENT, n, MeasureUnit.MONTHS)


FINE = PunishmentTerm(PunishmentKind.FINE, 20000, MeasureUnit.RUBLES)


def card(*episodes, final=None, conditional=False):
    return PrecedentCard(
        episodes=tuple(PrecedentEpisode(q, term) for q, term in episodes),
        mitigating=frozenset(),
        aggravating=frozenset(),
        recidivism=None,
        applied_general=frozenset({"73"}) if conditional else frozenset(),
        final=final,
        conditional=conditional,
        fabula="",
    )


def verdict(card_id, the_card):
    return PracticeVerdict(
        card_id=card_id,
        card=the_card,
        court_name="Условный районный суд",
        decision_date=date(2026, 3, card_id % 28 + 1),
        source_url=f"https://example.invalid/doc/{card_id}",
        uid=f"uid-{card_id}",
    )


FRAUD_4 = Qualification("159", 4)
FRAUD_3 = Qualification("159", 3)
THEFT_2B = Qualification("158", 2, "в")
THEFT_2A = Qualification("158", 2, "а")


class ParseQuestionTest(unittest.TestCase):
    def test_average_term_by_part_and_article(self):
        question = parse_practice_term_question("Какой средний срок по ч. 4 ст. 159?")
        self.assertEqual(question, PracticeTermQuestion(FRAUD_4))

    def test_words_and_point(self):
        question = parse_practice_term_question(
            "медианное наказание по пункту «в» части 2 статьи 158 УК РФ"
        )
        self.assertEqual(question, PracticeTermQuestion(THEFT_2B))

    def test_typical_imprisonment(self):
        question = parse_practice_term_question("Сколько обычно дают по ст. 228.1 ч. 4")
        self.assertEqual(question, PracticeTermQuestion(Qualification("228.1", 4)))

    def test_no_statistics_word_is_not_a_fact_question(self):
        self.assertIsNone(parse_practice_term_question("Какой срок по ч. 4 ст. 159?"))

    def test_no_term_word_is_not_a_fact_question(self):
        self.assertIsNone(parse_practice_term_question("Средний ущерб по ч. 4 ст. 159"))

    def test_no_qualification_is_not_guessed(self):
        self.assertIsNone(parse_practice_term_question("Какой средний срок за мошенничество?"))

    def test_several_qualifications_are_ambiguous(self):
        self.assertIsNone(
            parse_practice_term_question("средний срок по ч. 4 ст. 159 и ч. 2 ст. 158")
        )
        self.assertIsNone(parse_practice_term_question("средний срок по пп. «а, в» ч. 2 ст. 158"))

    def test_general_part_article_is_not_a_qualification(self):
        self.assertIsNone(parse_practice_term_question("средний срок по ч. 2 ст. 68"))


class CoversTest(unittest.TestCase):
    def test_part_question_covers_every_point_of_the_part(self):
        self.assertTrue(covers(Qualification("158", 2), THEFT_2B))
        self.assertTrue(covers(Qualification("158", 2), THEFT_2A))

    def test_point_question_needs_the_same_point(self):
        self.assertTrue(covers(THEFT_2B, THEFT_2B))
        self.assertFalse(covers(THEFT_2B, THEFT_2A))
        self.assertFalse(covers(THEFT_2B, Qualification("158", 2)))

    def test_other_part_or_article_is_not_covered(self):
        self.assertFalse(covers(FRAUD_4, FRAUD_3))
        self.assertFalse(covers(FRAUD_4, Qualification("159.1", 4)))
        self.assertFalse(covers(FRAUD_4, Qualification("159")))

    def test_article_question_covers_every_part(self):
        self.assertTrue(covers(Qualification("159"), FRAUD_4))


class FactsTest(unittest.TestCase):
    def test_single_count_verdict_uses_its_final_or_own_term(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4),
            [
                verdict(1, card((FRAUD_4, months(36)))),
                verdict(2, card((FRAUD_4, None), final=months(48))),
            ],
        )
        self.assertEqual(facts.found, 2)
        self.assertEqual(facts.excluded, 0)
        self.assertEqual([c.months for c in facts.counted], [36, 48])
        self.assertEqual(facts.mean_months, 42)
        self.assertEqual(facts.comparison.median_months, 42)

    def test_multi_count_verdict_uses_only_the_matching_counts_own_term(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4),
            [verdict(1, card((FRAUD_4, months(30)), (THEFT_2B, months(12)), final=months(36)))],
        )
        self.assertEqual([c.months for c in facts.counted], [30])

    def test_aggregate_term_is_never_attributed_to_one_count(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4),
            [verdict(1, card((FRAUD_4, None), (THEFT_2B, None), final=months(36)))],
        )
        self.assertEqual([c.months for c in facts.counted], [None])
        self.assertEqual(facts.comparison.with_term, 0)
        self.assertIsNone(facts.mean_months)

    def test_several_matching_counts_are_excluded_and_reported(self):
        facts = practice_term_facts(
            PracticeTermQuestion(Qualification("158", 2)),
            [verdict(1, card((THEFT_2A, months(20)), (THEFT_2B, months(24))))],
        )
        self.assertEqual(facts.found, 1)
        self.assertEqual(facts.excluded, 1)
        self.assertEqual(facts.counted, ())

    def test_cards_without_the_qualification_are_not_found(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4), [verdict(1, card((FRAUD_3, months(24))))]
        )
        self.assertEqual((facts.found, facts.excluded, facts.counted), (0, 0, ()))

    def test_milder_kind_has_no_term_but_is_counted(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4), [verdict(1, card((FRAUD_4, FINE)))]
        )
        self.assertEqual(len(facts.counted), 1)
        self.assertIsNone(facts.counted[0].months)
        self.assertEqual(facts.comparison.total, 1)
        self.assertEqual(facts.comparison.with_term, 0)

    def test_each_counted_verdict_keeps_its_provenance(self):
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4),
            [verdict(7, card((FRAUD_4, months(24)), conditional=True))],
        )
        counted = facts.counted[0]
        self.assertEqual(counted.card_id, 7)
        self.assertEqual(counted.source_url, "https://example.invalid/doc/7")
        self.assertEqual(counted.uid, "uid-7")
        self.assertEqual(counted.court_name, "Условный районный суд")
        self.assertTrue(counted.conditional)
        self.assertEqual(facts.comparison.conditional_share, 1.0)

    def test_enough_data_needs_the_practice_minimum(self):
        few = [verdict(i, card((FRAUD_4, months(12 + i)))) for i in range(4)]
        self.assertFalse(practice_term_facts(PracticeTermQuestion(FRAUD_4), few).enough_data)
        five = few + [verdict(9, card((FRAUD_4, months(40))))]
        self.assertTrue(practice_term_facts(PracticeTermQuestion(FRAUD_4), five).enough_data)

    def test_fractional_terms_are_kept(self):
        days = PunishmentTerm(PunishmentKind.IMPRISONMENT, 45, MeasureUnit.DAYS)
        facts = practice_term_facts(
            PracticeTermQuestion(FRAUD_4),
            [verdict(1, card((FRAUD_4, days))), verdict(2, card((FRAUD_4, months(2))))],
        )
        self.assertEqual(facts.mean_months, 1.75)


class DescribeTest(unittest.TestCase):
    def test_nothing_found_says_so_and_gives_no_numbers(self):
        text = describe_practice_term_facts(practice_term_facts(PracticeTermQuestion(FRAUD_4), []))
        self.assertIn("ч. 4 ст. 159 УК РФ", text)
        self.assertIn("нет приговоров", text)
        self.assertNotIn("медиана", text)

    def test_few_terms_are_not_called_practice(self):
        verdicts = [verdict(i, card((FRAUD_4, months(12 + i)))) for i in range(3)]
        text = describe_practice_term_facts(
            practice_term_facts(PracticeTermQuestion(FRAUD_4), verdicts)
        )
        self.assertIn("3 приговора", text)
        self.assertIn("недостаточно", text)
        self.assertNotIn("медиана", text)
        self.assertNotIn("среднее", text)

    def test_enough_terms_give_mean_median_range_and_conditional_share(self):
        terms = [12, 18, 24, 30, 36, 48]
        verdicts = [
            verdict(i, card((FRAUD_4, months(t)), conditional=i < 3)) for i, t in enumerate(terms)
        ]
        verdicts.append(verdict(10, card((FRAUD_4, months(20)), (FRAUD_4, months(22)))))
        text = describe_practice_term_facts(
            practice_term_facts(PracticeTermQuestion(FRAUD_4), verdicts)
        )
        self.assertIn("7 приговоров", text)
        self.assertIn("учтено 6", text)
        self.assertIn("исключён 1", text)
        self.assertIn("среднее 2 г. 4 мес.", text)
        self.assertIn("медиана 2 г. 3 мес.", text)
        self.assertIn("от 1 г. до 4 г.", text)
        self.assertIn("условно — 50%", text)
        self.assertIn("посчитаны кодом", text)

    def test_fractional_months_are_shown_with_one_decimal(self):
        days = PunishmentTerm(PunishmentKind.IMPRISONMENT, 45, MeasureUnit.DAYS)
        verdicts = [verdict(i, card((FRAUD_4, days))) for i in range(5)]
        text = describe_practice_term_facts(
            practice_term_facts(PracticeTermQuestion(FRAUD_4), verdicts)
        )
        self.assertIn("среднее 1,5 мес.", text)


if __name__ == "__main__":
    unittest.main()
