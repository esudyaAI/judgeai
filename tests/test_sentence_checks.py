"""ст. 68 per count and ст. 73 are added to the analysis from the read operative part (T13)."""

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    SanctionRole,
    StatutorySanction,
)

from src.schemas.analysis import Circumstance, LegalCheck, LlmCaseFacts
from src.schemas.criminal_sanctions import SanctionProvenance
from src.services.case_analyzer import assemble_analysis
from src.services.criminal_sanction_lookup import StatuteSanctionReading
from src.services.sentence_checks import build_sentence_checks, recidivism_of

PROVENANCE = SanctionProvenance(
    edition_id=1,
    edition_label="Synthetic edition",
    source_url="https://pravo.gov.ru/test-fixture",
    source_sha256="0" * 64,
    verification_status="unreviewed",
    provision_locator="article.158",
    parser_version="test",
)
REF = ArticleReference("158", 2)
IMPRISONMENT = PunishmentKind.IMPRISONMENT


def _reading(max_months=60, extra_kind=None):
    sanctions = [
        StatutorySanction(
            "158", 2, IMPRISONMENT, SanctionRole.MAIN, None, max_months, MeasureUnit.MONTHS, "..."
        )
    ]
    if extra_kind is not None:
        sanctions.append(
            StatutorySanction("158", 2, extra_kind, SanctionRole.MAIN, None, None, None, "...")
        )
    return StatuteSanctionReading(sanctions=sanctions, provenance=PROVENANCE)


def _term(months, kind=IMPRISONMENT):
    return PunishmentTerm(kind, months, MeasureUnit.MONTHS)


def _sentence(months=20, conditional=False, probation=None, quote="лишение свободы", final=None):
    count = CountSentence("п. «в» ч. 2 ст. 158 УК РФ", REF, _term(months), (), quote)
    return ImposedSentence(
        counts=(count,), final=final, conditional=conditional, probation_months=probation
    )


def _recidivism(value="simple", status="ok"):
    return [LegalCheck(norm="ст. 18 УК РФ", status=status, explanation="", source="", value=value)]


def test_recidivism_is_taken_only_from_a_confirmed_art18_check():
    assert recidivism_of(_recidivism("dangerous")).value == "dangerous"
    assert recidivism_of(_recidivism("simple", status="insufficient_data")).value == "unknown"
    assert recidivism_of(_recidivism("garbage")).value == "unknown"
    assert recidivism_of([]).value == "unknown"


def test_term_below_one_third_with_recidivism_is_flagged_per_count():
    [check] = build_sentence_checks(_sentence(months=19), {REF: _reading()}, _recidivism(), [])
    assert check.status == "possible_violation"
    assert check.norm.endswith("п. «в» ч. 2 ст. 158 УК РФ")
    assert "pravo.gov.ru/test-fixture" in check.source
    assert check.evidence == ["лишение свободы"]


def test_art61_mitigation_allows_a_term_below_one_third():
    mitigating = [Circumstance(name="Явка с повинной", norm="п. «и» ч. 1 ст. 61")]
    [check] = build_sentence_checks(
        _sentence(months=12), {REF: _reading()}, _recidivism(), mitigating
    )
    assert check.status == "ok" and "ч. 3 ст. 68" in check.explanation


def test_art64_in_the_operative_part_lifts_the_minimum():
    sentence = _sentence(months=6, quote="с применением ст. 64 УК РФ лишение свободы")
    [check] = build_sentence_checks(sentence, {REF: _reading()}, _recidivism(), [])
    assert check.status == "ok"


def test_unknown_sanction_gives_insufficient_data_not_a_violation():
    [check] = build_sentence_checks(_sentence(months=6), {}, _recidivism(), [])
    assert check.status == "insufficient_data"


def test_life_imprisonment_in_the_sanction_is_not_modelled():
    reading = _reading(extra_kind=PunishmentKind.LIFE_IMPRISONMENT)
    [check] = build_sentence_checks(_sentence(months=6), {REF: reading}, _recidivism(), [])
    assert check.status == "insufficient_data"


def test_no_art68_check_without_established_recidivism():
    assert (
        build_sentence_checks(_sentence(months=1), {REF: _reading()}, _recidivism("none"), []) == []
    )
    assert build_sentence_checks(_sentence(months=1), {REF: _reading()}, [], []) == []


def test_conditional_sentence_gets_an_art73_check():
    sentence = _sentence(months=24, conditional=True, probation=70)
    [check] = build_sentence_checks(sentence, {}, [], [])
    assert check.norm.startswith("Условное осуждение")
    assert check.status == "possible_violation"  # 70 months exceeds ч. 3 even without history
    assert "испытательный срок 70 мес." in check.value


def test_dangerous_recidivism_and_conditional_sentence_give_both_checks():
    sentence = _sentence(months=30, conditional=True, probation=24)
    checks = build_sentence_checks(sentence, {REF: _reading()}, _recidivism("dangerous"), [])
    assert [c.status for c in checks] == ["ok", "possible_violation"]
    assert "п. «в»" in checks[1].explanation


def test_final_term_is_used_for_art73_when_present():
    sentence = _sentence(months=30, conditional=True, probation=24, final=_term(120))
    [check] = build_sentence_checks(sentence, {}, [], [])
    assert check.status == "possible_violation" and "8 лет" in check.explanation


def test_empty_sentence_adds_nothing():
    assert build_sentence_checks(None, {}, _recidivism(), []) == []
    assert build_sentence_checks(ImposedSentence(), {}, _recidivism(), []) == []


def test_assemble_analysis_includes_the_sentence_checks():
    analysis = assemble_analysis(
        LlmCaseFacts.model_validate({"fabula": "Кража", "sanction_max_months": 60}),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=["Подсудимый действовал умышленно."],
        sentence=_sentence(months=24, conditional=True, probation=70),
        count_statutes={REF: _reading()},
    )
    norms = [check.norm for check in analysis.legal_checks]
    assert any(norm.startswith("Условное осуждение") for norm in norms)


def _art15(value="grave"):
    return LegalCheck(norm="ст. 15 УК РФ", status="ok", explanation="", source="", value=value)


REAL_TEXT = (
    "Подсудимый Иванов, ранее не судимый. Признать Иванова виновным и назначить наказание "
    "в виде лишения свободы с отбыванием в исправительной колонии строгого режима."
)


def test_wrong_regime_is_flagged_with_its_quote():
    checks = build_sentence_checks(
        _sentence(months=24),
        {},
        [_art15("grave"), *_recidivism("none")],
        [],
        document_text=REAL_TEXT,
        guilt="intentional",
    )
    [regime] = [c for c in checks if c.norm.startswith("Вид исправительного")]
    assert regime.status == "possible_violation"
    assert "колония общего режима" in regime.explanation
    assert "исправительной колонии строгого режима" in regime.evidence
    assert "ранее не судимый" in regime.evidence


def test_regime_needs_a_confirmed_category():
    checks = build_sentence_checks(
        _sentence(months=24),
        {},
        _recidivism("none"),
        [],
        document_text=REAL_TEXT,
        guilt="intentional",
    )
    [regime] = [c for c in checks if c.norm.startswith("Вид исправительного")]
    assert regime.status == "insufficient_data"


def test_no_regime_check_when_no_institution_is_named_or_sentence_is_conditional():
    plain = build_sentence_checks(
        _sentence(months=24),
        {},
        [_art15()],
        [],
        document_text="Подсудимый виновен.",
        guilt="intentional",
    )
    assert not [c for c in plain if c.norm.startswith("Вид исправительного")]
    conditional = build_sentence_checks(
        _sentence(months=24, conditional=True, probation=24),
        {},
        [_art15()],
        [],
        document_text=REAL_TEXT,
        guilt="intentional",
    )
    assert not [c for c in conditional if c.norm.startswith("Вид исправительного")]
