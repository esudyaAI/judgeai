"""T45.7 — the category of a crime (ст. 15 УК РФ) by code from the sanction in the law base."""

import unittest
from datetime import date

from legal_core.entities import (
    Category,
    Guilt,
    MeasureUnit,
    PunishmentKind,
    SanctionRole,
    StatutorySanction,
)
from legal_core.precedents import Qualification

from src.application.category_facts import answer_category_fact
from src.application.practice_chat import CATEGORY, SANCTION, answer_practice_question
from src.domain.category_facts import (
    CategoryFacts,
    CategoryQuestion,
    describe_category_date_note,
    describe_category_facts,
    describe_category_source,
    parse_category_question,
    part_categories,
)
from src.domain.fact_answer_scope import case_documents_note
from src.domain.reference_conflict import ReferenceDataConflict
from src.domain.sanction_facts import (
    SanctionSource,
    asked_date,
    asks_category,
    parse_sanction_question,
)

MAIN, ADDITIONAL = SanctionRole.MAIN, SanctionRole.ADDITIONAL
MONTHS = MeasureUnit.MONTHS


def sanction(kind, high=None, *, role=MAIN, unit=MONTHS, part=2, article="158"):
    return StatutorySanction(article, part, kind, role, None, high, unit, "синтетический текст")


def prison(high, **kw):
    return sanction(PunishmentKind.IMPRISONMENT, high, **kw)


SOURCE = SanctionSource(
    "Синтетическая редакция", "https://example.invalid/uk", "article.158", "unreviewed"
)
PART_2 = Qualification("158", 2)


def facts(sanctions, qualification=PART_2, guilt=None, **kw):
    return CategoryFacts(CategoryQuestion(qualification, guilt), tuple(sanctions), SOURCE, **kw)


class ParseTest(unittest.TestCase):
    def test_category_questions_are_recognised(self):
        for text in (
            "К какой категории относится ч. 2 ст. 158?",
            "Какая категория преступления по ч. 2 ст. 158 УК РФ?",
            "Какой тяжести преступление по ч. 2 ст. 158?",
            "Категория преступления, предусмотренного ч. 2 ст. 158",
            "Степень тяжести ч. 2 ст. 158",
        ):
            with self.subTest(text=text):
                parsed = parse_category_question(text)
                self.assertEqual(parsed, CategoryQuestion(PART_2, None))

    def test_form_of_guilt_is_taken_only_when_the_question_names_one(self):
        intent = parse_category_question("Категория умышленного преступления по ч. 2 ст. 158")
        negligent = parse_category_question("Категория по ч. 1 ст. 109, по неосторожности")
        both = parse_category_question("Категория ч. 1 ст. 109 — умышленное или неосторожное?")
        self.assertEqual(intent.guilt, Guilt.INTENTIONAL)
        self.assertEqual(negligent.guilt, Guilt.NEGLIGENT)
        self.assertIsNone(both.guilt)

    def test_point_question_is_decided_by_its_part(self):
        parsed = parse_category_question("Категория п. «в» ч. 2 ст. 158?")
        self.assertEqual(parsed.qualification, Qualification("158", 2, "в"))
        self.assertEqual(parsed.target, PART_2)

    def test_not_a_category_question(self):
        for text in (
            "Какая санкция по ч. 2 ст. 158?",
            "Какая санкция за вред здоровью небольшой тяжести по ч. 1 ст. 115?",  # harm
            "Какой средний срок по ч. 2 ст. 158 для этой категории?",  # statistics
            "К какой категории относится кража?",  # no qualification
            "Категория ч. 2 ст. 158 и ч. 1 ст. 161?",  # two qualifications
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_category_question(text))

    def test_severity_words_do_not_hide_a_category_question(self):  # T45.8
        text = "К какой категории относится ч. 1 ст. 112 — средней тяжести?"
        parsed = parse_category_question(text)
        self.assertEqual(parsed, CategoryQuestion(Qualification("112", 1), None))

    def test_category_question_is_not_a_sanction_question(self):
        text = "Категория преступления, предусмотренного ч. 2 ст. 158"
        self.assertTrue(asks_category(text))
        self.assertIsNone(parse_sanction_question(text))
        harm = "Какая санкция за вред здоровью небольшой тяжести по ч. 1 ст. 115?"
        self.assertFalse(asks_category(harm))
        self.assertEqual(parse_sanction_question(harm).qualification, Qualification("115", 1))


class DescribeTest(unittest.TestCase):
    def test_same_category_for_both_forms_of_guilt(self):
        text = describe_category_facts(
            facts([sanction(PunishmentKind.FINE, 200_000, unit=MeasureUnit.RUBLES), prison(60)])
        )
        self.assertEqual(
            text,
            "Категория по ст. 15 УК РФ — по наибольшему основному наказанию санкции из базы "
            "законов:\nч. 2 ст. 158 УК РФ: наибольший срок лишения свободы — 5 г.; "
            "преступление средней тяжести при любой форме вины.",
        )

    def test_additional_punishment_does_not_raise_the_category(self):
        items = part_categories(
            facts([prison(24), prison(120, role=ADDITIONAL)])  # synthetic: only main counts
        )
        self.assertEqual(
            items[0].categories,
            ((Guilt.INTENTIONAL, Category.SMALL), (Guilt.NEGLIGENT, Category.SMALL)),
        )

    def test_category_that_depends_on_guilt_states_both_and_says_why(self):
        text = describe_category_facts(facts([prison(96)]))
        self.assertIn(
            "наибольший срок лишения свободы — 8 г.; если умышленное — тяжкое преступление; "
            "если по неосторожности — преступление средней тяжести.",
            text,
        )
        self.assertIn("Категория зависит от формы вины", text)

    def test_named_guilt_gives_one_category(self):
        text = describe_category_facts(facts([prison(96)], guilt=Guilt.NEGLIGENT))
        self.assertIn("преступление средней тяжести (по неосторожности).", text)
        self.assertNotIn("зависит от формы вины", text)

    def test_life_imprisonment_and_beyond_the_negligent_limit(self):
        life = describe_category_facts(
            facts([prison(240), sanction(PunishmentKind.LIFE_IMPRISONMENT, unit=None)])
        )
        self.assertIn(
            "в санкции есть пожизненное лишение свободы; если умышленное — особо тяжкое "
            "преступление; если по неосторожности — ст. 15 категории не определяет.",
            life,
        )
        long_term = part_categories(facts([prison(240)], guilt=Guilt.NEGLIGENT))
        self.assertEqual(long_term[0].categories, ((Guilt.NEGLIGENT, None),))

    def test_sanction_without_imprisonment_is_small(self):
        text = describe_category_facts(
            facts([sanction(PunishmentKind.FINE, 80_000, unit=MeasureUnit.RUBLES)])
        )
        self.assertIn(
            "лишения свободы среди основных наказаний санкции нет; преступление небольшой "
            "тяжести при любой форме вины.",
            text,
        )

    def test_whole_article_lists_every_part_and_unparsed_main_sanction(self):
        sanctions = [
            prison(60, part=2),
            prison(24, part=1),
            sanction(PunishmentKind.RESTRICTION_OF_FREEDOM, 12, role=ADDITIONAL, part=3),
        ]
        lines = describe_category_facts(facts(sanctions, Qualification("158"))).splitlines()
        self.assertTrue(
            lines[1].startswith("ч. 1 ст. 158 УК РФ: наибольший срок лишения свободы — 2 г.")
        )
        self.assertTrue(lines[2].startswith("ч. 2 ст. 158 УК РФ:"))
        self.assertEqual(
            lines[3],
            "ч. 3 ст. 158 УК РФ: основные наказания санкции не разобраны — категорию "
            "определить нельзя.",
        )

    def test_point_unparsed_and_conflict(self):
        point = describe_category_facts(facts([prison(60)], Qualification("158", 2, "в")))
        self.assertTrue(point.endswith("Для п. «в» действует санкция всей части."))
        missing = describe_category_facts(facts([]))
        self.assertEqual(
            missing,
            "В базе законов санкция ч. 2 ст. 158 УК РФ не разобрана: категорию определить нельзя.",
        )
        conflict = describe_category_facts(facts([], conflict=True))
        self.assertIn("Конфликт справочных данных по ч. 2 ст. 158 УК РФ", conflict)

    def test_source_names_the_edition_and_the_art15_rule(self):
        source = describe_category_source(facts([prison(60)]))
        lines = source.splitlines()
        self.assertTrue(
            lines[0].startswith("Источник: Синтетическая редакция, https://example.invalid/uk")
        )
        self.assertTrue(lines[1].startswith("Категорию считает правило программы по ст. 15 УК РФ"))
        self.assertIn("consultant.ru", lines[1])
        self.assertEqual(describe_category_source(facts([])), "")


class Readings:
    def __init__(self, result):
        self.result, self.asked = result, []

    async def article_sanctions(self, article, part):
        self.asked.append((article, part))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Phraser:
    def __init__(self):
        self.calls = []

    async def phrase(self, qualification, facts_text):
        self.calls.append(qualification)
        return "По ч. 2 ст. 158 — особо тяжкое преступление."


QUESTION = "К какой категории относится ч. 2 ст. 158?"


class UseCaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_not_a_question_reads_nothing(self):
        readings = Readings(None)
        self.assertIsNone(await answer_category_fact(readings, "Какая санкция по ч. 2 ст. 158?"))
        self.assertEqual(readings.asked, [])

    async def test_the_part_is_read_and_categorised(self):
        readings = Readings(([prison(60)], SOURCE))
        answer = await answer_category_fact(readings, "Категория п. «в» ч. 2 ст. 158?")
        self.assertEqual(readings.asked, [("158", 2)])
        self.assertIn("преступление средней тяжести", answer.text)
        self.assertIn("https://example.invalid/uk", answer.source)
        self.assertNotIn("example.invalid", answer.text)

    async def test_unparsed_and_conflicting_readings(self):
        missing = await answer_category_fact(Readings(None), QUESTION)
        self.assertIn("не разобрана", missing.text)
        self.assertEqual(missing.source, "")
        answer = await answer_category_fact(Readings(ReferenceDataConflict("две")), QUESTION)
        self.assertTrue(answer.facts.conflict)
        self.assertIn("Конфликт справочных данных", answer.text)


class ChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_category_question_in_the_chat_is_answered_by_code_not_reworded(self):
        phraser = Phraser()
        answer = await answer_practice_question(
            None, QUESTION, phraser, Readings(([prison(60)], SOURCE))
        )
        self.assertEqual(answer.kind, CATEGORY)
        self.assertFalse(answer.worded_by_model)
        self.assertEqual(phraser.calls, [])  # the category word is not checkable by numbers
        self.assertIn("преступление средней тяжести при любой форме вины.", answer.text)
        self.assertIn("Категорию считает правило программы", answer.text)

    async def test_sanction_question_stays_a_sanction_question(self):
        answer = await answer_practice_question(
            None, "Какая санкция по ч. 2 ст. 158?", None, Readings(([prison(60)], SOURCE))
        )
        self.assertEqual(answer.kind, SANCTION)

    async def test_without_readings_a_category_question_is_not_answered(self):
        self.assertIsNone(await answer_practice_question(None, QUESTION, None))

    def test_note_in_a_chat_with_case_documents(self):
        note = case_documents_note(CATEGORY, has_case_documents=True)
        self.assertIn("форма вины", note)
        self.assertIn("дата преступления", note)
        self.assertIsNone(case_documents_note(CATEGORY, has_case_documents=False))


PRISON_5 = (prison(60),)


def dated(on_text, start=None, end=None, sanctions=PRISON_5, **kw):
    source = SanctionSource(
        "Синтетическая редакция",
        "https://example.invalid/uk",
        "article.158",
        "unreviewed",
        effective_from=date.fromisoformat(start) if start else None,
        effective_to=date.fromisoformat(end) if end else None,
    )
    question = CategoryQuestion(PART_2, None, asked_date(on_text))
    return CategoryFacts(question, tuple(sanctions), source, **kw)


class DatedCategoryTest(unittest.TestCase):  # T45.10
    def test_the_date_of_the_question_is_read(self):
        for text in (
            "К какой категории относилась ч. 2 ст. 158 на 01.03.2020?",
            "Категория преступления по ч. 2 ст. 158 по состоянию на 1 марта 2020 г.",
        ):
            with self.subTest(text=text):
                parsed = parse_category_question(text)
                self.assertEqual(parsed.qualification, PART_2)
                self.assertEqual(parsed.asked.on, date(2020, 3, 1))
        self.assertIsNone(parse_category_question(QUESTION).asked)
        self.assertTrue(parse_category_question("Категория ч. 2 ст. 158 в 2019 году").asked.unclear)

    def test_in_force_on_the_date_gives_the_category_and_says_what_was_not_checked(self):
        item = dated("на 01.03.2020", start="2019-01-01")
        text = describe_category_facts(item)
        self.assertIn("преступление средней тяжести при любой форме вины", text)
        note = describe_category_date_note(item)
        self.assertTrue(note.startswith("По периоду действия в базе законов (с 01.01.2019)"))
        self.assertIn("действовало на 01.03.2020", note)
        self.assertIn("ст. 9–10 УК РФ", note)
        self.assertIn("редакция ст. 15", note)  # the art. 15 rule itself is not dated

    def test_not_in_force_on_the_date_gives_no_category(self):
        for start, end in (("2021-01-01", None), ("2019-01-01", "2020-03-01")):
            with self.subTest(start=start, end=end):
                item = dated("на 01.03.2020", start=start, end=end)
                text = describe_category_facts(item)
                self.assertTrue(text.startswith("На 01.03.2020 положение article.158"))
                self.assertIn("не действовало", text)
                self.assertIn("категорию определить нельзя", text)
                self.assertNotIn("тяжести", text)
                self.assertEqual(describe_category_date_note(item), "")

    def test_unknown_period_and_unclear_date_are_said(self):
        unknown = describe_category_date_note(dated("на 01.03.2020"))
        self.assertTrue(unknown.startswith("Период действия положения в базе законов не задан"))
        self.assertIn("на 01.03.2020", unknown)
        unclear = describe_category_date_note(dated("в 2019 году", start="2019-01-01"))
        self.assertTrue(unclear.startswith("В вопросе не одна точная дата"))
        self.assertIn("редакция ст. 15", unclear)

    def test_no_note_without_a_date_or_without_an_answer(self):
        self.assertEqual(describe_category_date_note(facts([prison(60)])), "")
        self.assertEqual(describe_category_date_note(dated("на 01.03.2020", sanctions=())), "")
        conflict = dated("на 01.03.2020", start="2019-01-01", sanctions=(), conflict=True)
        self.assertEqual(describe_category_date_note(conflict), "")


class DatedCategoryChatTest(unittest.IsolatedAsyncioTestCase):  # T45.10
    async def test_the_note_is_written_by_code_between_the_answer_and_the_source(self):
        dated_source = SanctionSource(
            "Синтетическая редакция",
            "https://example.invalid/uk",
            "article.158",
            "unreviewed",
            effective_from=date(2019, 1, 1),
        )
        readings = Readings(([prison(60)], dated_source))
        question = "К какой категории относилась ч. 2 ст. 158 на 01.03.2020?"
        answer = await answer_category_fact(readings, question)
        self.assertTrue(answer.date_note.startswith("По периоду действия"))
        chat = await answer_practice_question(None, question, Phraser(), readings)
        self.assertEqual(chat.kind, CATEGORY)
        body = chat.text.index("преступление средней тяжести")
        note = chat.text.index(answer.date_note)
        source = chat.text.index("Источник:")
        self.assertLess(body, note)
        self.assertLess(note, source)

    async def test_not_in_force_in_the_chat_names_no_category(self):
        refused = SanctionSource(
            "Синтетическая редакция",
            "https://example.invalid/uk",
            "article.158",
            "unreviewed",
            effective_from=date(2021, 1, 1),
        )
        question = "Какой тяжести преступление по ч. 2 ст. 158 на 01.03.2020?"
        readings = Readings(([prison(60)], refused))
        chat = await answer_practice_question(None, question, None, readings)
        self.assertIn("категорию определить нельзя", chat.text)
        self.assertNotIn("средней тяжести", chat.text)


if __name__ == "__main__":
    unittest.main()
