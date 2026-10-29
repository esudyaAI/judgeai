"""The analysis uses the statutory sanction from the imported УК РФ text, not the model's guess."""

from legal_core.entities import MeasureUnit, PunishmentKind, SanctionRole, StatutorySanction

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
    provision_locator="article.158",
    parser_version="test",
)


def _sanction(kind, part=2, role=SanctionRole.MAIN, max_value=None, unit=None):
    return StatutorySanction("158", part, kind, role, None, max_value, unit, "наказывается ...")


def _statute(*sanctions):
    return StatuteSanctionReading(sanctions=list(sanctions), provenance=PROVENANCE)


def _analyse(statute, facts=None, text="Подсудимый действовал умышленно."):
    data = {"fabula": "Кража", "sanction_max_months": 48, "recommended_months": 50}
    data.update(facts or {})
    return assemble_analysis(
        LlmCaseFacts.model_validate(data),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        statute=statute,
    )


PART_2 = _statute(
    _sanction(PunishmentKind.FINE, max_value=200_000, unit=MeasureUnit.RUBLES),
    _sanction(PunishmentKind.IMPRISONMENT, max_value=60, unit=MeasureUnit.MONTHS),
    _sanction(
        PunishmentKind.RESTRICTION_OF_FREEDOM,
        role=SanctionRole.ADDITIONAL,
        max_value=12,
        unit=MeasureUnit.MONTHS,
    ),
)


def test_statutory_maximum_overrides_model_value_with_warning():
    result = _analyse(PART_2)
    assert result.scale.sanction_max_months == 60
    assert result.scale.within_sanction is True
    assert any("по тексту УК РФ — 60 мес." in w for w in result.warnings)
    assert any("pravo.gov.ru/test-fixture" in w and "unreviewed" in w for w in result.warnings)


def test_sanction_check_lists_main_alternatives_with_source():
    check = _analyse(PART_2).legal_checks[0]
    assert check.norm == "Санкция ч. 2 ст. 158 УК РФ"
    assert check.value == "штраф до 200 000 ₽; лишение свободы до 5 г."
    assert check.source == "https://pravo.gov.ru/test-fixture"
    assert check.needs_legal_review


def test_art15_category_uses_statutory_ceiling():
    legal = {"guilt": {"value": "intentional", "quote": "действовал умышленно"}}
    checks = {c.norm: c for c in _analyse(PART_2, {"legal_facts": legal}).legal_checks}
    assert checks["ст. 15 УК РФ"].status == "ok"
    assert checks["ст. 15 УК РФ"].value == "medium"


def test_without_part_the_statute_is_not_applied():
    statute = _statute(
        _sanction(PunishmentKind.IMPRISONMENT, part=1, max_value=24, unit=MeasureUnit.MONTHS),
        _sanction(PunishmentKind.IMPRISONMENT, part=2, max_value=60, unit=MeasureUnit.MONTHS),
    )
    result = _analyse(statute)
    assert result.scale.sanction_max_months == 48
    assert any("не указана часть" in w for w in result.warnings)
    assert all(not c.norm.startswith("Санкция") for c in result.legal_checks)


def test_no_statute_keeps_model_value_flagged_as_unverified():
    result = _analyse(None)
    assert result.scale.sanction_max_months == 48
    assert any("не сверен со справочником" in w for w in result.warnings)


def _mitigated(imposed_quote, imposed_months, text):
    return _analyse(
        PART_2,
        {
            "mitigating": [{"name": "Явка с повинной", "norm": "п. «и» ч. 1 ст. 61"}],
            "legal_facts": {
                "imposed_imprisonment_months": {"value": imposed_months, "quote": imposed_quote}
            },
        },
        text=text + " Суд признаёт явку с повинной смягчающим обстоятельством. "
        "Отягчающих обстоятельств не установлено.",
    )


def test_imposed_term_above_art62_limit_is_flagged():
    text = "назначить наказание в виде лишения свободы на срок 4 года 6 месяцев условно"
    checks = {c.norm: c for c in _mitigated("на срок 4 года 6 месяцев", 54, text).legal_checks}
    check = checks["Назначенное наказание: пределы санкции и ч. 1 ст. 62 УК РФ"]
    assert check.status == "possible_violation"
    assert "40 мес." in check.explanation
    assert check.value == "54 мес." and check.evidence == ["на срок 4 года 6 месяцев"]


def test_imposed_term_with_fabricated_quote_is_not_checked():
    checks = {
        c.norm: c
        for c in _mitigated(
            "на срок 3 года", 36, "назначить лишение свободы на 2 года"
        ).legal_checks
    }
    check = checks["Назначенное наказание: пределы санкции и ч. 1 ст. 62 УК РФ"]
    assert check.status == "insufficient_data" and check.value is None


def _per_count(
    sentence,
    statutes,
    text=(
        "Суд признаёт явку с повинной смягчающим обстоятельством. "
        "Отягчающих обстоятельств не установлено."
    ),
    model_texts=None,
):
    return assemble_analysis(
        LlmCaseFacts.model_validate(
            {
                "fabula": "Кражи",
                "mitigating": [{"name": "Явка с повинной", "norm": "п. «и» ч. 1 ст. 61"}],
            }
        ),
        prompt="",
        documents=1,
        pages=1,
        seconds=1,
        similar_items=[],
        extra_warnings=[],
        document_texts=[text],
        sentence=sentence,
        count_statutes=statutes,
        model_texts=model_texts,
    )


def test_each_count_is_checked_against_its_own_sanction():
    from legal_core.entities import (
        ArticleReference,
        CountSentence,
        ImposedSentence,
        PunishmentTerm,
    )

    part2 = ArticleReference("158", 2)
    unknown = ArticleReference("999", 1)
    months = lambda n: PunishmentTerm(PunishmentKind.IMPRISONMENT, n, MeasureUnit.MONTHS)  # noqa: E731
    sentence = ImposedSentence(
        counts=(
            CountSentence("п. «в» ч. 2 ст. 158 УК РФ", part2, months(54), (), "на срок 4 года 6"),
            CountSentence("ч. 2 ст. 158 УК РФ", part2, months(30), (), "на срок 2 года 6"),
            CountSentence("ч. 1 ст. 999 УК РФ", unknown, months(12), (), "на срок 1 год"),
        ),
        final=months(60),
        aggregation_rule="ч. 2 ст. 69 УК РФ",
        final_quote="окончательно 5 лет",
    )
    result = _per_count(sentence, {part2: PART_2})
    by_norm = {c.norm: c for c in result.legal_checks}
    sanction_checks = [c for c in result.legal_checks if c.norm.startswith("Санкция")]
    assert len(sanction_checks) == 1
    first = by_norm[
        "Назначенное наказание: пределы санкции и ч. 1 ст. 62 УК РФ · п. «в» ч. 2 ст. 158 УК РФ"
    ]
    second = by_norm[
        "Назначенное наказание: пределы санкции и ч. 1 ст. 62 УК РФ · ч. 2 ст. 158 УК РФ"
    ]
    assert first.status == "possible_violation" and first.value == "лишение свободы 4 г. 6 мес."
    assert second.status == "ok"
    assert by_norm["Назначенное наказание · ч. 1 ст. 999 УК РФ"].status == "insufficient_data"
    final = by_norm["Окончательное наказание (ч. 2 ст. 69 УК РФ)"]
    assert final.status == "insufficient_data" and final.evidence == ["окончательно 5 лет"]
    read = result.imposed_sentence
    assert [c.imprisonment_months for c in read.counts] == [54, 30, 12]
    assert read.final == "лишение свободы 5 г." and read.aggregation_rule == "ч. 2 ст. 69 УК РФ"


def test_shortened_model_text_is_reported():
    result = _per_count(None, {}, text="длинный текст приговора", model_texts=["короткий"])
    assert any("сокращена описательная часть" in w for w in result.warnings)
    assert result.imposed_sentence is None
