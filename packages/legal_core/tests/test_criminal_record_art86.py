"""Conviction + ст. 86: whether a prior record exists on the day of the new offence (T3.1)."""

import unittest
from datetime import date

from legal_core.criminal_record import Conviction, CriminalRecord, active_at, classify_record
from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import CurrentOffence, Recidivism
from legal_core.rules.art86 import Disposition, SentenceForExpungement

GRAVE_REAL = CurrentOffence(Guilt.INTENTIONAL, Category.GRAVE, True)


def sentence(**kwargs):
    # п. «в» ч. 3 ст. 86: средней тяжести, лишение свободы — три года после отбытия.
    values = dict(
        category=Category.MEDIUM,
        disposition=Disposition.IMPRISONMENT,
        offence_date=date(2018, 1, 15),
        minor_at_offence=False,
        legal_force_date=date(2018, 6, 1),
        served_on=date(2020, 6, 1),
    )
    values.update(kwargs)
    return SentenceForExpungement(**values)


def conviction(active=None, expungement=None, **kwargs):
    values = dict(
        judgment_id="one",
        guilt=Guilt.INTENTIONAL,
        category=Category.MEDIUM,
        offence_date=date(2018, 1, 15),
        legal_force_date=date(2018, 6, 1),
        imprisoned_by_sentence=True,
        conditional_or_deferred=False,
        sent_to_prison_on=None,
        active_at_offence=active,
        expungement=expungement,
    )
    values.update(kwargs)
    return Conviction(**values)


class ActiveAtTest(unittest.TestCase):
    def test_without_sentence_facts_the_caller_value_is_used(self):
        for value in (True, False, None):
            with self.subTest(value=value):
                self.assertIs(active_at(conviction(active=value), date(2022, 1, 1)), value)

    def test_record_computed_by_art86_before_expungement(self):
        # Отбыто 01.06.2020, погашается 01.06.2023: на 10.05.2022 судимость есть.
        self.assertIs(active_at(conviction(expungement=sentence()), date(2022, 5, 10)), True)

    def test_record_computed_by_art86_after_expungement(self):
        self.assertIs(active_at(conviction(expungement=sentence()), date(2023, 6, 2)), False)

    def test_last_day_of_the_term_is_undecided(self):
        self.assertIsNone(active_at(conviction(expungement=sentence()), date(2023, 6, 1)))

    def test_unknown_served_date_is_undecided(self):
        facts = sentence(served_on=None)
        self.assertIsNone(active_at(conviction(expungement=facts), date(2022, 5, 10)))

    def test_matching_caller_value_is_kept(self):
        self.assertIs(
            active_at(conviction(active=True, expungement=sentence()), date(2022, 5, 10)), True
        )

    def test_conflict_with_caller_value_is_undecided(self):
        # Caller says the record was expunged, ст. 86 says it still exists: no silent choice.
        self.assertIsNone(
            active_at(conviction(active=False, expungement=sentence()), date(2022, 5, 10))
        )

    def test_caller_value_fills_a_boundary_the_rule_cannot_decide(self):
        # E.g. an ИЦ МВД certificate established the fact; the rule alone returns None.
        self.assertIs(
            active_at(conviction(active=True, expungement=sentence()), date(2023, 6, 1)), True
        )

    def test_released_from_punishment_is_not_a_record(self):
        facts = sentence(released_from_punishment=True)
        self.assertIs(active_at(conviction(expungement=facts), date(2022, 5, 10)), False)


class ConsistencyTest(unittest.TestCase):
    def test_category_must_match(self):
        with self.assertRaises(ValueError):
            conviction(expungement=sentence(category=Category.GRAVE))

    def test_legal_force_date_must_match(self):
        with self.assertRaises(ValueError):
            conviction(expungement=sentence(legal_force_date=date(2018, 7, 1)))

    def test_unknown_legal_force_date_on_one_side_is_allowed(self):
        conviction(legal_force_date=None, expungement=sentence())
        conviction(expungement=sentence(legal_force_date=None))

    def test_offence_date_must_match(self):
        with self.assertRaises(ValueError):
            conviction(expungement=sentence(offence_date=date(2018, 2, 1)))

    def test_conditional_flag_must_match_disposition(self):
        with self.assertRaises(ValueError):
            conviction(
                expungement=sentence(
                    disposition=Disposition.CONDITIONAL, served_on=None, probation_months=24
                )
            )


class RecidivismWithExpungementTest(unittest.TestCase):
    def record(self, facts):
        return CriminalRecord(
            birth_date=date(1990, 3, 3), convictions=(conviction(expungement=facts),), complete=True
        )

    def test_active_record_gives_simple_recidivism(self):
        result = classify_record(self.record(sentence()), GRAVE_REAL, date(2022, 5, 10))
        self.assertEqual(result, Recidivism.SIMPLE)

    def test_expunged_record_gives_no_recidivism(self):
        result = classify_record(self.record(sentence()), GRAVE_REAL, date(2023, 6, 2))
        self.assertEqual(result, Recidivism.NONE)

    def test_boundary_day_gives_unknown(self):
        result = classify_record(self.record(sentence()), GRAVE_REAL, date(2023, 6, 1))
        self.assertEqual(result, Recidivism.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
