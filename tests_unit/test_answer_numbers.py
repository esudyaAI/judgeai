"""T45.2 — a model may word a practice answer but never add a number to it."""

import unittest

from src.domain.answer_numbers import number_tokens, unsupported_numbers

FACTS = (
    "По ч. 4 ст. 159 УК РФ в базе практики 6 приговоров, учтено 5. Срок лишения свободы "
    "известен в 5 из 5: среднее 2 г., медиана 2 г., от 1 г. до 3 г., половина сроков — "
    "от 1 г. 6 мес. до 2 г. 6 мес.; условно — 40% учтённых."
)


class NumberTokensTest(unittest.TestCase):
    def test_digits_decimals_and_percent(self):
        self.assertEqual(number_tokens("2,5 мес. и 40% из 1159"), {"2.5", "40", "1159"})

    def test_grouped_thousands_are_one_number(self):
        self.assertEqual(number_tokens("1 159 приговоров"), {"1159"})
        self.assertEqual(number_tokens("1 159"), {"1159"})

    def test_separate_small_numbers_stay_separate(self):
        self.assertEqual(number_tokens("от 1 г. 6 мес."), {"1", "6"})

    def test_numeral_words_are_numbers(self):
        self.assertEqual(
            number_tokens("Пять приговоров, двух лет, полтора года"), {"пять", "двух", "полтора"}
        )
        self.assertEqual(number_tokens("тридцать месяцев, четверть"), {"тридцать", "четверть"})

    def test_ordinary_words_are_not_numbers(self):
        self.assertEqual(number_tokens("сторона, стоит, пятница, одновременно, двое суток"), set())

    def test_yo_is_e(self):
        self.assertEqual(number_tokens("трёх"), number_tokens("трех"))


class UnsupportedNumbersTest(unittest.TestCase):
    def test_rewording_with_the_same_numbers_is_accepted(self):
        answer = (
            "В базе 6 приговоров по ч. 4 ст. 159 УК РФ, из них учтено 5. Средний срок — 2 г., "
            "медиана — 2 г., разброс от 1 г. до 3 г.; условно назначено в 40% случаев, "
            "половина сроков от 1 г. 6 мес. до 2 г. 6 мес."
        )
        self.assertEqual(unsupported_numbers(answer, FACTS), frozenset())

    def test_recomputed_term_is_refused(self):
        answer = "Средний срок — 24 месяца, медиана 2 г."
        self.assertEqual(unsupported_numbers(answer, FACTS), {"24"})

    def test_rounded_or_invented_figure_is_refused(self):
        self.assertEqual(unsupported_numbers("примерно 2,1 г.", FACTS), {"2.1"})
        self.assertEqual(unsupported_numbers("из 7 приговоров", FACTS), {"7"})

    def test_spelled_number_absent_from_facts_is_refused(self):
        self.assertEqual(unsupported_numbers("пять приговоров", FACTS), {"пять"})

    def test_spelled_number_present_in_facts_is_accepted(self):
        self.assertEqual(unsupported_numbers("половина сроков", FACTS), frozenset())

    def test_grouping_does_not_hide_a_number(self):
        self.assertEqual(unsupported_numbers("1 159 приговоров", "1159 приговоров"), frozenset())


if __name__ == "__main__":
    unittest.main()
