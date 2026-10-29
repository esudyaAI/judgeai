from src.services.verdict_segmenter import segment_verdict
from tests.fixtures.synthetic_verdicts import (
    MULTI_COUNT,
    NO_HEADINGS,
    OTHER_KINDS,
    SINGLE_CONDITIONAL,
)


def test_spaced_headings_split_three_parts():
    segments = segment_verdict(MULTI_COUNT)
    assert segments.recognized
    assert "ранее судимого" in segments.introduction
    assert "тайно похитил с банковского счёта" in segments.description
    assert segments.operative.startswith("К. признать виновным")
    assert "окончательно назначить" in segments.operative
    assert "П Р И Г О В О Р И Л" not in segments.operative


def test_plain_and_lowercase_headings():
    plain = segment_verdict(SINGLE_CONDITIONAL)
    lower = segment_verdict(OTHER_KINDS)
    assert plain.recognized and "ст. 73" in plain.operative
    assert lower.recognized and lower.introduction == ""
    assert "обязательных работ" in lower.operative


def test_text_without_headings_is_kept_whole_as_description():
    segments = segment_verdict(NO_HEADINGS)
    assert not segments.recognized
    assert segments.description == NO_HEADINGS
    assert segments.operative == ""


def test_parts_cover_the_whole_text():
    segments = segment_verdict(MULTI_COUNT)
    total = len(segments.introduction) + len(segments.description) + len(segments.operative)
    assert total <= len(MULTI_COUNT) and total > 0.9 * len(MULTI_COUNT)


def test_model_context_keeps_operative_part_when_trimmed():
    segments = segment_verdict(MULTI_COUNT)
    context = segments.model_context(limit=1300)
    assert len(context) <= 1300
    assert "окончательно назначить" in context
    assert "ранее судимого" in context
    assert "[…]" in context


def test_word_in_running_text_is_not_a_heading():
    text = "Суд установил, что вина доказана. Суд приговорил к штрафу ранее."
    assert not segment_verdict(text).recognized


def test_inline_heading_with_colon():
    text = "Вводная часть суд УСТАНОВИЛ: фабула дела. Суд ПРИГОВОРИЛ: назначить штраф."
    segments = segment_verdict(text)
    assert segments.introduction == "Вводная часть суд"
    assert segments.description == "фабула дела. Суд"
    assert segments.operative == "назначить штраф."


def test_collegiate_feminine_headings_preserve_operative_part():
    text = (
        "Вводная часть.\nУСТАНОВИЛА:\nОбстоятельства.\nП Р И Г О В О Р И Л А:\nНазначить наказание."
    )
    result = segment_verdict(text)
    assert result.introduction == "Вводная часть."
    assert result.description == "Обстоятельства."
    assert result.operative == "Назначить наказание."
    assert not segment_verdict("Коллегия приговорила подсудимого ранее.").recognized
