"""T45.2 — a practice question in the chat: numbers by code, wording by a model if it adds none."""

import unittest
from datetime import date

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm
from legal_core.precedents import PrecedentCard, PrecedentEpisode, Qualification

from src.application.practice_chat import answer_practice_question
from src.application.similar_precedents import StoredCard
from src.domain.practice_facts import (
    PracticeTermFacts,
    PracticeTermQuestion,
    PracticeVerdict,
    practice_term_facts,
)
from src.domain.practice_sources import describe_practice_sources

THEFT_2 = Qualification("158", 2)


def months(n):
    return PunishmentTerm(PunishmentKind.IMPRISONMENT, n, MeasureUnit.MONTHS)


def card(term, conditional=False):
    return PrecedentCard(
        episodes=(PrecedentEpisode(THEFT_2, term),),
        mitigating=frozenset(),
        aggravating=frozenset(),
        recidivism=None,
        applied_general=frozenset({"73"}) if conditional else frozenset(),
        final=None,
        conditional=conditional,
        fabula="",
    )


def stored(card_id, term, day=None, conditional=False):
    return StoredCard(
        id=card_id,
        card=card(term, conditional),
        knowledge_verdict_id=card_id,
        uid=f"uid-{card_id}",
        court_name="Условный районный суд",
        decision_date=day or date(2026, 1, card_id),
        source_url=f"https://example.invalid/doc/{card_id}",
    )


FIVE = [stored(i, months(m)) for i, m in enumerate((12, 18, 24, 30, 36), start=1)]


class Store:
    def __init__(self, cards):
        self.cards, self.asked = cards, []

    async def cards_with_article(self, article):
        self.asked.append(article)
        return self.cards


class Phraser:
    def __init__(self, wording):
        self.wording, self.calls = wording, []

    async def phrase(self, qualification, facts_text):
        self.calls.append((qualification, facts_text))
        return self.wording


QUESTION = "Какой средний срок по ч. 2 ст. 158?"


class AnswerPracticeQuestionTest(unittest.IsolatedAsyncioTestCase):
    async def test_not_a_fact_question_is_left_to_the_chat(self):
        store, phraser = Store(FIVE), Phraser("любой текст")
        self.assertIsNone(await answer_practice_question(store, "Проверь проект", phraser))
        self.assertEqual((store.asked, phraser.calls), ([], []))

    async def test_without_a_model_the_code_wording_and_sources_are_shown(self):
        answer = await answer_practice_question(Store(FIVE), QUESTION, None)
        self.assertFalse(answer.worded_by_model)
        self.assertIn("среднее 2 г.", answer.text)
        self.assertIn("Источники", answer.text)
        for i in range(1, 6):
            self.assertIn(f"https://example.invalid/doc/{i}", answer.text)

    async def test_model_wording_with_the_same_numbers_is_shown(self):
        phraser = Phraser("Средний срок по ч. 2 ст. 158 — 2 г., медиана 2 г. (5 приговоров).")
        answer = await answer_practice_question(Store(FIVE), QUESTION, phraser)
        self.assertTrue(answer.worded_by_model)
        self.assertTrue(answer.text.startswith("Средний срок по ч. 2 ст. 158 — 2 г."))
        self.assertIn("https://example.invalid/doc/1", answer.text)  # sources still by code
        qualification, facts_text = phraser.calls[0]
        self.assertEqual(qualification, "ч. 2 ст. 158 УК РФ")
        self.assertIn("среднее 2 г.", facts_text)
        self.assertNotIn("example.invalid", facts_text)  # the model gets no source list

    async def test_model_wording_with_an_added_number_is_not_shown(self):
        phraser = Phraser("Обычно дают около 24 месяцев.")
        answer = await answer_practice_question(Store(FIVE), QUESTION, phraser)
        self.assertFalse(answer.worded_by_model)
        self.assertEqual(answer.rejected_numbers, {"24"})
        self.assertNotIn("24 месяцев", answer.text)
        self.assertIn("среднее 2 г.", answer.text)

    async def test_no_usable_wording_falls_back_to_code(self):
        for wording in (None, "", "   "):
            answer = await answer_practice_question(Store(FIVE), QUESTION, Phraser(wording))
            self.assertFalse(answer.worded_by_model)
            self.assertIn("среднее 2 г.", answer.text)

    async def test_no_verdicts_no_sources(self):
        answer = await answer_practice_question(Store([]), QUESTION, None)
        self.assertIn("нет приговоров", answer.text)
        self.assertNotIn("Источники", answer.text)


def facts_of(cards) -> PracticeTermFacts:
    verdicts = [
        PracticeVerdict(s.id, s.card, s.court_name, s.decision_date, s.source_url, s.uid)
        for s in cards
    ]
    return practice_term_facts(PracticeTermQuestion(THEFT_2), verdicts)


class SourcesTest(unittest.TestCase):
    def test_newest_first_with_court_date_uid_term_and_link(self):
        text = describe_practice_sources(facts_of(FIVE))
        lines = text.splitlines()
        self.assertEqual(len(lines), 6)
        self.assertEqual(
            lines[1],
            "1. Условный районный суд, 05.01.2026, УИД uid-5, 3 г., https://example.invalid/doc/5",
        )
        self.assertTrue(lines[5].startswith("5. Условный районный суд, 01.01.2026"))

    def test_conditional_and_unknown_term_and_missing_origin(self):
        cards = [
            stored(1, months(18), conditional=True),
            StoredCard(2, card(None), 2, None, None, None, None),
        ]
        lines = describe_practice_sources(facts_of(cards)).splitlines()
        self.assertIn("1 г. 6 мес. условно", lines[1])
        self.assertEqual(
            lines[2], "2. суд не указан, срок лишения свободы не назначен или не распознан"
        )

    def test_long_list_is_cut_and_the_rest_counted(self):
        cards = [stored(i, months(12), day=date(2025, 1, 1)) for i in range(1, 14)]
        lines = describe_practice_sources(facts_of(cards), limit=10).splitlines()
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[-1], "…и ещё 3 учтено в расчёте, в список не вошли.")
        self.assertTrue(lines[1].startswith("1. ") and lines[1].endswith("doc/1"))

    def test_nothing_counted_nothing_listed(self):
        self.assertEqual(describe_practice_sources(facts_of([])), "")


if __name__ == "__main__":
    unittest.main()
