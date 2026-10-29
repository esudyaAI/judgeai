"""A verdict on an attempt and a second offence with a final term by ст. 70 (synthetic data).

The final term of several offences is checked by ст. 69/70, not against the sanction of one count;
an attempt is bounded by ч. 3 ст. 66; every count's article reaches the qualification.
"""

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
    StatutorySanction,
    Unfinished,
)

from src.schemas.analysis import LlmCaseFacts
from src.schemas.criminal_sanctions import SanctionProvenance
from src.services.case_analyzer import assemble_analysis
from src.services.criminal_sanction_lookup import StatuteSanctionReading

PROVENANCE = SanctionProvenance(
    edition_id=1,
    edition_label="Synthetic edition",
    source_url="https://pravo.gov.ru/test-fixture",
    source_sha256="0" * 64,
    verification_status="unreviewed",
    provision_locator="article",
    parser_version="test",
)
ROBBERY = ArticleReference("161", 1)
HARM = ArticleReference("111", 2)
TEXT = (
    "Иванов И.И. умышленно, из корыстных побуждений пытался открыто похитить товар. "
    "В его действиях в силу п. «а» ч. 3 ст. 18 УК РФ усматривается особо опасный рецидив "
    "преступлений."
)


def _reading(article, part, max_months):
    sanction = StatutorySanction(
        article,
        part,
        PunishmentKind.IMPRISONMENT,
        SanctionRole.MAIN,
        None,
        max_months,
        MeasureUnit.MONTHS,
        "наказывается лишением свободы",
    )
    return StatuteSanctionReading(sanctions=[sanction], provenance=PROVENANCE)


def _months(n):
    return PunishmentTerm(PunishmentKind.IMPRISONMENT, n, MeasureUnit.MONTHS)


def _facts(**extra):
    return LlmCaseFacts.model_validate(
        {
            "fabula": "Покушение на грабёж и причинение тяжкого вреда здоровью",
            "qualification": {"article": "ч. 3 ст. 30, ч. 1 ст. 161 УК РФ", "title": "Покушение"},
            "aggravating": [{"name": "Рецидив", "norm": "п. «а» ч. 1 ст. 63"}],
            **extra,
        }
    )


def _analyse(sentence, statutes, facts):
    return assemble_analysis(
        facts,
        prompt="",
        documents=1,
        pages=0,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[TEXT],
        statute=statutes[ROBBERY],
        sentence=sentence,
        count_statutes=statutes,
    )


ATTEMPT = CountSentence(
    "ч. 3 ст. 30, ч.1 ст.161 УК РФ", ROBBERY, _months(18), (), "полтора года", Unfinished.ATTEMPT
)
SECOND = CountSentence("п. «а,з» ч.2 ст.111 УК РФ", HARM, _months(48), (), "четыре года")
STATUTES = {ROBBERY: _reading("161", 1, 48), HARM: _reading("111", 2, 120)}


def test_final_term_of_several_offences_is_checked_by_art70_not_by_one_sanction():
    sentence = ImposedSentence(
        counts=(ATTEMPT, SECOND),
        final=_months(57),
        aggregation_rule="ст. 70 УК РФ",
        final_quote="окончательное наказание назначить",
    )
    result = _analyse(sentence, STATUTES, _facts(recommended_months=57))
    assert result.scale is None
    assert not any("выходит за допустимый предел" in w for w in result.warnings)
    checks = {c.norm: c for c in result.legal_checks}
    final = checks["Окончательное наказание (ст. 70 УК РФ)"]
    assert final.status == "insufficient_data" and final.value == "лишение свободы 4 г. 9 мес."
    assert "не прочитаны" in final.explanation or "не угадан" in final.explanation
    attempt = checks[
        "Назначенное наказание: пределы санкции и ч. 3 ст. 66 УК РФ · ч. 3 ст. 30, ч.1 ст.161 УК РФ"
    ]
    assert attempt.status == "ok"


def test_every_count_reaches_the_qualification_and_art15_takes_the_most_serious():
    sentence = ImposedSentence(counts=(ATTEMPT, SECOND))
    result = _analyse(sentence, STATUTES, _facts())
    assert "ст.111" in result.qualification.article.replace(" ", "")
    assert result.qualification.article.startswith("ч. 3 ст. 30, ч. 1 ст. 161 УК РФ")
    art15 = next(c for c in result.legal_checks if c.norm == "ст. 15 УК РФ")
    assert art15.status == "ok" and art15.value == "grave"
    assert "из текста приговора" in art15.explanation


def test_recidivism_minimum_for_an_attempt_is_a_third_of_the_reduced_maximum():
    short = CountSentence(
        "ч. 3 ст. 30, ч.1 ст.161 УК РФ", ROBBERY, _months(13), (), "год", Unfinished.ATTEMPT
    )
    result = _analyse(ImposedSentence(counts=(short,)), STATUTES, _facts())
    art68 = next(c for c in result.legal_checks if c.norm.startswith("Срок наказания при рецидиве"))
    # one third of 36 is 12 months: 13 is within; one third of 48 (16) would wrongly flag it.
    assert art68.status == "ok"
    assert "ч. 3 ст. 66" in art68.explanation


def test_single_attempt_scale_is_bounded_by_art66():
    result = _analyse(ImposedSentence(counts=(ATTEMPT,)), STATUTES, _facts(recommended_months=40))
    assert result.scale.limit_months == 36 and result.scale.limit_norm == "ч. 3 ст. 66"
    assert any("выходит за допустимый предел" in w for w in result.warnings)


def test_service_keys_of_variants_become_words():
    variants = [
        {"label": "offense_1", "title": "Эпизод: покушение", "details": "", "rationale": ""},
        {"label": "aggregate_crimes", "title": "По совокупности", "details": "", "rationale": ""},
        {
            "label": "final_sentence",
            "title": "Окончательное наказание",
            "details": "final_sentence: 4 года 9 месяцев",
            "rationale": "",
        },
    ]
    result = _analyse(ImposedSentence(counts=(ATTEMPT,)), STATUTES, _facts(variants=variants))
    labels = [v.label for v in result.variants]
    assert labels == ["Эпизод 1", "По совокупности преступлений", "Окончательное"]
    assert "final_sentence" not in result.variants[2].details


def test_art70_uses_intermediate_art69_and_known_unserved_balance():
    sentence = ImposedSentence(
        counts=(ATTEMPT, SECOND),
        final=_months(57),
        aggregation_rule="ст. 70 УК РФ",
        intermediate=_months(54),
        intermediate_rule="ч. 3 ст. 69 УК РФ",
        intermediate_quote="совокупность 54 месяца",
        unserved=_months(12),
        unserved_quote="неотбытая часть 12 месяцев",
        joined=_months(3),
        joined_quote="присоединить 3 месяца",
        final_quote="Окончательно 57 месяцев",
    )
    result = _analyse(sentence, STATUTES, _facts())
    final = next(
        c for c in result.legal_checks if c.norm == "Окончательное наказание (ст. 70 УК РФ)"
    )
    assert final.status == "ok" and "12 месяцев" in " ".join(final.evidence)
    assert result.imposed_sentence.intermediate == "лишение свободы 4 г. 6 мес."
