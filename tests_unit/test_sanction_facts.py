"""T45.3 — «what does the law provide»: the sanction of the part from the law base, by code."""

import unittest

from legal_core.entities import MeasureUnit, PunishmentKind, SanctionRole, StatutorySanction
from legal_core.precedents import Qualification

from src.application.practice_chat import SANCTION, answer_practice_question
from src.application.sanction_facts import answer_sanction_fact
from src.domain.reference_conflict import ReferenceDataConflict
from src.domain.sanction_facts import (
    SanctionFacts,
    SanctionQuestion,
    SanctionSource,
    describe_alternative,
    describe_sanction_facts,
    describe_sanction_source,
    parse_sanction_question,
)

MAIN, ADDITIONAL = SanctionRole.MAIN, SanctionRole.ADDITIONAL


def sanction(kind, role=MAIN, low=None, high=None, unit=MeasureUnit.MONTHS, part=2):
    return StatutorySanction("158", part, kind, role, low, high, unit, "синтетический текст")


THEFT_2 = (
    sanction(PunishmentKind.FINE, high=200_000, unit=MeasureUnit.RUBLES),
    sanction(PunishmentKind.COMPULSORY_WORKS, high=480, unit=MeasureUnit.HOURS),
    sanction(PunishmentKind.IMPRISONMENT, high=60),
    sanction(PunishmentKind.RESTRICTION_OF_FREEDOM, ADDITIONAL, high=12),
)
SOURCE = SanctionSource(
    "Синтетическая редакция", "https://example.invalid/uk", "article.158", "unreviewed"
)


THEFT_2_PART = Qualification("158", 2)


def facts(sanctions=THEFT_2, qualification=THEFT_2_PART, source=SOURCE, **kw):
    return SanctionFacts(SanctionQuestion(qualification), tuple(sanctions), source, **kw)


class ParseTest(unittest.TestCase):
    def test_sanction_questions_are_recognised(self):
        for text in (
            "Какая санкция по ч. 2 ст. 158?",
            "Что грозит по ч. 2 ст. 158 УК РФ?",
            "Какое наказание предусмотрено ч. 2 ст. 158?",
            "Как наказывается кража по ч. 2 ст. 158",
            "Какое наказание по закону за ч. 2 ст. 158?",
        ):
            with self.subTest(text=text):
                parsed = parse_sanction_question(text)
                self.assertEqual(parsed.qualification, Qualification("158", 2))

    def test_point_question_asks_for_the_sanction_of_its_part(self):
        parsed = parse_sanction_question("Какая санкция по п. «в» ч. 2 ст. 158?")
        self.assertEqual(parsed.qualification, Qualification("158", 2, "в"))
        self.assertEqual(parsed.target, Qualification("158", 2))

    def test_not_a_sanction_question(self):
        for text in (
            "Какой средний срок по ч. 2 ст. 158?",  # statistics: a practice question
            "Какая средняя санкция по ч. 2 ст. 158?",
            "Проверь проект приговора по ч. 2 ст. 158",  # no sanction word
            "Какая санкция за кражу?",  # no qualification
            "Какая санкция по ч. 2 ст. 158 и ч. 1 ст. 161?",  # two qualifications
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_sanction_question(text))


class DescribeTest(unittest.TestCase):
    def test_main_and_additional_alternatives_with_bounds_from_the_base(self):
        text = describe_sanction_facts(facts())
        self.assertEqual(
            text,
            "Санкция по базе законов (как в тексте редакции):\n"
            "ч. 2 ст. 158 УК РФ: основные наказания — штраф до 200 000 ₽; "
            "обязательные работы до 480 ч.; лишение свободы до 5 г.; "
            "дополнительные — ограничение свободы до 1 г.",
        )

    def test_alternative_bounds(self):
        cases = [
            (
                sanction(PunishmentKind.IMPRISONMENT, low=24, high=78),
                "лишение свободы от 2 г. до 6 г. 6 мес.",
            ),
            (sanction(PunishmentKind.ARREST, high=6), "арест до 6 мес."),
            (sanction(PunishmentKind.LIFE_IMPRISONMENT, unit=None), "пожизненное лишение свободы"),
            (sanction(PunishmentKind.FINE, unit=MeasureUnit.RUBLES), "штраф"),
            (sanction(PunishmentKind.FINE, high=2.5, unit=MeasureUnit.RUBLES), "штраф до 2,5 ₽"),
            (sanction(PunishmentKind.ARREST, high=15, unit=MeasureUnit.DAYS), "арест до 15 дн."),
        ]
        for item, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(describe_alternative(item), expected)

    def test_whole_article_lists_every_part_in_order(self):
        sanctions = [
            sanction(PunishmentKind.IMPRISONMENT, high=60, part=2),
            sanction(PunishmentKind.IMPRISONMENT, high=24, part=1),
        ]
        text = describe_sanction_facts(facts(sanctions, Qualification("158")))
        lines = text.splitlines()
        self.assertTrue(
            lines[1].startswith("ч. 1 ст. 158 УК РФ: основные наказания — лишение свободы до 2 г.")
        )
        self.assertTrue(lines[2].startswith("ч. 2 ст. 158 УК РФ:"))

    def test_article_without_parts_and_only_additional_parsed(self):
        sanctions = [
            sanction(PunishmentKind.RESTRICTION_OF_FREEDOM, ADDITIONAL, high=12, part=None)
        ]
        text = describe_sanction_facts(facts(sanctions, Qualification("158")))
        self.assertIn("ст. 158 УК РФ: основные наказания — в разборе нет; дополнительные", text)

    def test_point_is_answered_by_the_part(self):
        text = describe_sanction_facts(facts(qualification=Qualification("158", 2, "в")))
        self.assertIn("ч. 2 ст. 158 УК РФ: основные", text)
        self.assertTrue(text.endswith("Для п. «в» действует санкция всей части."))

    def test_unparsed_part_and_conflict_are_said_not_guessed(self):
        self.assertEqual(
            describe_sanction_facts(facts(())),
            "В базе законов санкция ч. 2 ст. 158 УК РФ не разобрана: ответ дать нельзя.",
        )
        conflict = describe_sanction_facts(facts((), source=None, conflict=True))
        self.assertTrue(conflict.startswith("Конфликт справочных данных по ч. 2 ст. 158 УК РФ"))
        self.assertIn("ни одна не выбрана", conflict)

    def test_source_names_the_edition_and_its_review(self):
        self.assertEqual(
            describe_sanction_source(facts()),
            "Источник: Синтетическая редакция, https://example.invalid/uk, положение "
            "article.158; редакция не сверена юристом (статус: unreviewed).",
        )
        verified = SanctionSource("Ред.", "https://example.invalid/uk", "article.158", "verified")
        self.assertTrue(
            describe_sanction_source(facts(source=verified)).endswith("сверена юристом.")
        )
        self.assertEqual(describe_sanction_source(facts(())), "")


class Readings:
    def __init__(self, result):
        self.result, self.asked = result, []

    async def article_sanctions(self, article, part):
        self.asked.append((article, part))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class UseCaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_not_a_question_reads_nothing(self):
        readings = Readings(None)
        self.assertIsNone(await answer_sanction_fact(readings, "Проверь проект"))
        self.assertEqual(readings.asked, [])

    async def test_the_part_is_read_and_described_with_its_source(self):
        readings = Readings((list(THEFT_2), SOURCE))
        answer = await answer_sanction_fact(readings, "Какая санкция по п. «в» ч. 2 ст. 158?")
        self.assertEqual(readings.asked, [("158", 2)])
        self.assertIn("лишение свободы до 5 г.", answer.text)
        self.assertIn("https://example.invalid/uk", answer.source)
        self.assertNotIn("example.invalid", answer.text)  # the source is not in the body

    async def test_unparsed_and_conflicting_readings(self):
        missing = await answer_sanction_fact(Readings(None), "Какая санкция по ч. 9 ст. 158?")
        self.assertIn("не разобрана", missing.text)
        self.assertEqual(missing.source, "")
        conflict = ReferenceDataConflict("две редакции")
        answer = await answer_sanction_fact(Readings(conflict), "Какая санкция по ч. 2 ст. 158?")
        self.assertTrue(answer.facts.conflict)
        self.assertIn("Конфликт справочных данных", answer.text)


class Phraser:
    def __init__(self, wording):
        self.wording, self.calls = wording, []

    async def phrase(self, qualification, facts_text):
        self.calls.append((qualification, facts_text))
        return self.wording


class PracticeStore:
    def __init__(self):
        self.asked = []

    async def cards_with_article(self, article):
        self.asked.append(article)
        return []


QUESTION = "Какая санкция по ч. 2 ст. 158?"


class ChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_sanction_question_in_the_chat_is_answered_by_code_with_the_source(self):
        store = PracticeStore()
        answer = await answer_practice_question(
            store, QUESTION, None, Readings((list(THEFT_2), SOURCE))
        )
        self.assertEqual(answer.kind, SANCTION)
        self.assertIsNone(answer.facts)
        self.assertIn("лишение свободы до 5 г.", answer.text)
        self.assertTrue(answer.text.endswith("(статус: unreviewed)."))
        self.assertEqual(store.asked, [])  # not a practice question: no practice read

    async def test_practice_question_goes_to_practice_even_with_sanctions(self):
        readings = Readings((list(THEFT_2), SOURCE))
        answer = await answer_practice_question(
            PracticeStore(), "Какой средний срок по ч. 2 ст. 158?", None, readings
        )
        self.assertEqual(answer.kind, "practice")
        self.assertEqual(readings.asked, [])

    async def test_without_readings_or_store(self):
        self.assertIsNone(await answer_practice_question(PracticeStore(), QUESTION, None))
        practice = "Какой средний срок по ч. 2 ст. 158?"
        self.assertIsNone(await answer_practice_question(None, practice, None, Readings(None)))
        answer = await answer_practice_question(
            None, QUESTION, None, Readings((list(THEFT_2), SOURCE))
        )
        self.assertEqual(answer.kind, SANCTION)

    async def test_model_wording_with_the_same_numbers_is_shown_source_by_code(self):
        phraser = Phraser("По ч. 2 ст. 158 — до 5 г. лишения свободы или штраф до 200 000 ₽.")
        answer = await answer_practice_question(
            None, QUESTION, phraser, Readings((list(THEFT_2), SOURCE))
        )
        self.assertTrue(answer.worded_by_model)
        self.assertTrue(answer.text.startswith("По ч. 2 ст. 158 — до 5 г."))
        self.assertIn("Источник: Синтетическая редакция", answer.text)
        self.assertNotIn("example.invalid", phraser.calls[0][1])

    async def test_model_wording_with_a_recomputed_bound_is_not_shown(self):
        phraser = Phraser("По ч. 2 ст. 158 — до пяти лет (60 месяцев).")
        answer = await answer_practice_question(
            None, QUESTION, phraser, Readings((list(THEFT_2), SOURCE))
        )
        self.assertFalse(answer.worded_by_model)
        self.assertEqual(answer.rejected_numbers, {"пяти", "60"})
        self.assertIn("лишение свободы до 5 г.", answer.text)


if __name__ == "__main__":
    unittest.main()
