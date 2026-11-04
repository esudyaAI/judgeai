import unittest
from dataclasses import replace

from src.domain.fact_review import FactDecision, InvalidReview, apply_decisions
from src.domain.prepared_legal import PreparedFact, PreparedLegalInputs, evaluate_legal_inputs
from src.domain.prepared_sentencing import PreparedSentencingInputs
from src.domain.review_evidence import (
    Evidence,
    InvalidEvidence,
    ReviewDocument,
    ReviewSources,
    SourceFingerprint,
    SourceRange,
    SubjectSource,
)


class FactReviewTest(unittest.TestCase):
    def setUp(self):
        self.doc = ReviewDocument(
            0, "synthetic", "Суд установил умысел. Сведения о судимостях неполные."
        )
        self.context = ReviewSources(
            (SourceFingerprint(0, self.doc.document_hash),),
            (SubjectSource(0, "Лицо 1", (SourceRange(0, 0, len(self.doc.text)),)),),
        )
        self.proof = Evidence(0, self.doc.document_hash, 0, 20, self.doc.text[:20])
        self.legal = {
            0: PreparedLegalInputs(
                category_guilt=PreparedFact("intentional", "умысел"),
                category_uses_text=True,
                history_complete=PreparedFact(False, "неполные"),
            )
        }
        self.sentencing = {0: PreparedSentencingInputs(None)}

    def apply(self, *decisions):
        return apply_decisions(self.legal, self.sentencing, (self.doc,), self.context, decisions)

    def test_unknown_clears_both_guilt_inputs_and_disables_text_fallback(self):
        legal, _, audit, changed = self.apply(
            FactDecision("subject/0/legal/guilt", "unknown", "Недостаточно доказательств")
        )
        self.assertIsNone(legal[0].model_guilt.value)
        self.assertIsNone(legal[0].category_guilt.value)
        self.assertFalse(legal[0].category_uses_text)
        self.assertTrue(changed)
        self.assertEqual(audit[0]["old_value"], "intentional")
        self.assertEqual(self.legal[0].category_guilt.value, "intentional")

    def test_false_confirmation_remains_false_and_does_not_invalidate_comparison(self):
        legal, _, audit, changed = self.apply(
            FactDecision(
                "subject/0/legal/history_complete", "confirm", "Сверено", evidence=self.proof
            )
        )
        self.assertIs(legal[0].history_complete.value, False)
        self.assertIs(audit[0]["new_value"], False)
        self.assertFalse(changed)

    def test_values_are_strict_and_paths_allowlisted(self):
        for value in (0, 1, "false", None, [], {}):
            with self.subTest(value=value), self.assertRaises(InvalidReview):
                self.apply(
                    FactDecision(
                        "subject/0/legal/history_complete", "correct", "Сверено", value, self.proof
                    )
                )
        for field in (
            "subject/0/legal/__dict__",
            "subject/1/legal/guilt",
            "subject/0/prior/0/guilt",
        ):
            with self.subTest(field=field), self.assertRaises(InvalidReview):
                self.apply(FactDecision(field, "unknown", "Нет сведений"))

    def test_unknown_prior_field_never_becomes_empty_history(self):
        self.legal[0] = replace(
            self.legal[0], prior_convictions=((("judgment_id", PreparedFact("J1", "Суд")),),)
        )
        legal, _, _, _ = self.apply(
            FactDecision("subject/0/prior/0/judgment_id", "unknown", "Не удалось установить")
        )
        self.assertEqual(len(legal[0].prior_convictions), 1)
        self.assertIsNone(dict(legal[0].prior_convictions[0])["judgment_id"].value)
        self.assertIsNone(evaluate_legal_inputs(legal[0]).recidivism)

    def test_wrong_quote_and_duplicate_decisions_rejected(self):
        decision = FactDecision(
            "subject/0/legal/guilt", "correct", "Сверено", "negligent", self.proof
        )
        with self.assertRaises(InvalidReview):
            self.apply(decision, decision)
        with self.assertRaises(InvalidEvidence):
            self.apply(replace(decision, evidence=replace(self.proof, quote="другая цитата")))

    def test_missing_source_reason_and_unknown_confirmation_rejected(self):
        for decision in (
            FactDecision("subject/0/legal/guilt", "correct", "Сверено", "negligent"),
            FactDecision("subject/0/legal/guilt", "unknown", " "),
            FactDecision("subject/0/legal/category", "confirm", "Сверено", evidence=self.proof),
            FactDecision("subject/0/legal/guilt", "unknown", "Причина", evidence=self.proof),
        ):
            with self.subTest(decision=decision), self.assertRaises(InvalidReview):
                self.apply(decision)

    def test_prior_correction_changes_classification_and_unknown_blocks_it(self):
        from src.domain.prepared_legal import PRIOR_FIELD_KINDS

        values = {name: True for name, _ in PRIOR_FIELD_KINDS}
        values.update(
            judgment_id="J1",
            guilt="intentional",
            category="grave",
            conditional_or_deferred=False,
            revoked_and_sent_before_offence=False,
        )
        self.legal[0] = PreparedLegalInputs(
            model_guilt=PreparedFact("intentional", "Суд"),
            category_guilt=PreparedFact("intentional", "Суд"),
            category=PreparedFact("grave", "Суд"),
            real_imprisonment=PreparedFact(True, "Суд"),
            history_complete=PreparedFact(True, "Суд"),
            prior_convictions=(
                tuple((name, PreparedFact(value, "Суд")) for name, value in values.items()),
            ),
        )
        self.assertEqual(evaluate_legal_inputs(self.legal[0]).recidivism, "dangerous")
        legal, _, _, _ = self.apply(
            FactDecision(
                "subject/0/prior/0/active_at_offence",
                "correct",
                "Судимость снята",
                False,
                self.proof,
            )
        )
        self.assertEqual(evaluate_legal_inputs(legal[0]).recidivism, "none")
        legal, _, _, _ = self.apply(
            FactDecision("subject/0/prior/0/active_at_offence", "unknown", "Дата не установлена")
        )
        self.assertIsNone(evaluate_legal_inputs(legal[0]).recidivism)

    def test_regime_correction_changes_core_check_without_parsing_text(self):
        from legal_core.entities import Category, Guilt
        from legal_core.rules.art18 import Recidivism

        from src.domain.prepared_sentencing import PreparedRegimeInputs, evaluate_regime_inputs

        regime = PreparedRegimeInputs(
            PreparedFact("strict", "Суд"),
            PreparedFact(True, "Суд"),
            PreparedFact(True, "Суд"),
            True,
        )
        self.sentencing[0] = replace(self.sentencing[0], regime=regime)
        check = evaluate_regime_inputs(regime, Recidivism.SIMPLE, Category.GRAVE, Guilt.INTENTIONAL)
        self.assertEqual(check.status.value, "ok")
        _, sentencing, _, _ = self.apply(
            FactDecision("subject/0/regime/male", "correct", "Сверено", False, self.proof)
        )
        changed = evaluate_regime_inputs(
            sentencing[0].regime, Recidivism.SIMPLE, Category.GRAVE, Guilt.INTENTIONAL
        )
        self.assertEqual(changed.status.value, "possible_violation")
        _, sentencing, _, _ = self.apply(
            FactDecision("subject/0/regime/imposed", "unknown", "Не удалось установить")
        )
        unknown = evaluate_regime_inputs(
            sentencing[0].regime, Recidivism.SIMPLE, Category.GRAVE, Guilt.INTENTIONAL
        )
        self.assertEqual(unknown.status.value, "insufficient_data")
