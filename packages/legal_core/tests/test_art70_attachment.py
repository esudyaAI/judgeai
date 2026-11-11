import pytest

from legal_core.checks import CheckStatus
from legal_core.rules import art70
from legal_core.rules.art70 import (
    AttachmentMethod,
    DraftSentenceAttachment,
    SentencesCumulationFacts,
    check_sentences_attachment,
)

FACTS = SentencesCumulationFacts(new_sentence_months=36, unserved_months=24, art56_part5=None)


def _draft(**changes):
    values = {
        "by_cumulation": True,
        "method": AttachmentMethod.PARTIAL,
        "final_term": 48,
        "imprisonment": True,
        "general_part_maximum": None,
    }
    values.update(changes)
    return DraftSentenceAttachment(**values)


def test_result_carries_its_own_rule_key_and_source():
    result = check_sentences_attachment(FACTS, _draft())
    assert result.rule_key == art70.ATTACHMENT_RULE_KEY == "art70.attachment"
    assert result.norm == art70.ATTACHMENT_NORM
    assert "ст. 70" in result.source and "sha256" in result.source
    assert result.needs_legal_review is True


def test_not_by_cumulation_is_ok_and_unknown_is_insufficient():
    assert check_sentences_attachment(FACTS, _draft(by_cumulation=False)).status is CheckStatus.OK
    unknown = check_sentences_attachment(FACTS, _draft(by_cumulation=None))
    assert unknown.status is CheckStatus.INSUFFICIENT_DATA


def test_life_imprisonment_and_unknown_final_term_are_insufficient():
    life = check_sentences_attachment(FACTS, _draft(life_imprisonment=True))
    assert life.status is CheckStatus.INSUFFICIENT_DATA
    assert "пожизненное" in life.explanation
    missing = check_sentences_attachment(FACTS, _draft(final_term=None))
    assert missing.status is CheckStatus.INSUFFICIENT_DATA


def test_partial_attachment_within_the_sum_is_ok():
    result = check_sentences_attachment(FACTS, _draft(final_term=59))
    assert result.status is CheckStatus.OK


def test_final_term_above_the_sum_is_a_violation_for_any_method():
    for method in (AttachmentMethod.PARTIAL, AttachmentMethod.FULL, None):
        result = check_sentences_attachment(FACTS, _draft(method=method, final_term=61))
        assert result.status is CheckStatus.POSSIBLE_VIOLATION, method
        assert "60 мес." in result.explanation and "ч. 1 ст. 70" in result.explanation


def test_full_attachment_must_equal_the_sum():
    assert (
        check_sentences_attachment(
            FACTS, _draft(method=AttachmentMethod.FULL, final_term=60)
        ).status
        is CheckStatus.OK
    )
    short = check_sentences_attachment(FACTS, _draft(method=AttachmentMethod.FULL, final_term=50))
    assert short.status is CheckStatus.POSSIBLE_VIOLATION
    assert "полностью" in short.explanation


def test_partial_attachment_equal_to_the_sum_contradicts_the_stated_method():
    result = check_sentences_attachment(FACTS, _draft(final_term=60))
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "частично" in result.explanation


def test_unknown_method_checks_only_the_sum():
    assert check_sentences_attachment(FACTS, _draft(method=None, final_term=60)).status is (
        CheckStatus.OK
    )


@pytest.mark.parametrize(
    "facts",
    [
        SentencesCumulationFacts(None, 24, None),
        SentencesCumulationFacts(36, None, None),
    ],
)
def test_unknown_terms_are_insufficient(facts):
    result = check_sentences_attachment(facts, _draft())
    assert result.status is CheckStatus.INSUFFICIENT_DATA
    assert "Не установлен" in result.explanation


def test_part2_less_severe_kind_within_general_part_maximum_is_ok():
    facts = SentencesCumulationFacts(12, 6, None)
    draft = _draft(final_term=16, imprisonment=False, general_part_maximum=24)
    assert check_sentences_attachment(facts, draft).status is CheckStatus.OK


def test_part2_less_severe_kind_above_general_part_maximum_is_a_violation():
    facts = SentencesCumulationFacts(20, 10, None)
    draft = _draft(final_term=26, imprisonment=False, general_part_maximum=24)
    result = check_sentences_attachment(facts, draft)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 2 ст. 70" in result.explanation and "24" in result.explanation


def test_part2_needs_the_general_part_maximum_and_the_kind():
    facts = SentencesCumulationFacts(12, 6, None)
    no_max = check_sentences_attachment(facts, _draft(final_term=16, imprisonment=False))
    assert no_max.status is CheckStatus.INSUFFICIENT_DATA
    assert "Общей частью" in no_max.explanation
    no_kind = check_sentences_attachment(facts, _draft(final_term=16, imprisonment=None))
    assert no_kind.status is CheckStatus.INSUFFICIENT_DATA


def test_imprisonment_ignores_the_general_part_maximum():
    draft = _draft(final_term=59, general_part_maximum=24)
    assert check_sentences_attachment(FACTS, draft).status is CheckStatus.OK


def test_all_known_violations_are_reported_even_with_gaps():
    facts = SentencesCumulationFacts(20, 10, None)
    draft = _draft(
        method=AttachmentMethod.FULL, final_term=31, imprisonment=False, general_part_maximum=24
    )
    result = check_sentences_attachment(facts, draft)
    assert result.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 1 ст. 70" in result.explanation and "ч. 2 ст. 70" in result.explanation
    gap_facts = SentencesCumulationFacts(None, 10, None)
    gap = check_sentences_attachment(gap_facts, draft)
    assert gap.status is CheckStatus.POSSIBLE_VIOLATION
    assert "ч. 2 ст. 70" in gap.explanation


@pytest.mark.parametrize(
    ("facts", "draft"),
    [
        (SentencesCumulationFacts(-1, 24, None), _draft()),
        (SentencesCumulationFacts(36, -1, None), _draft()),
        (FACTS, _draft(final_term=-1)),
        (FACTS, _draft(imprisonment=False, general_part_maximum=0)),
    ],
)
def test_negative_terms_and_non_positive_maximum_are_rejected(facts, draft):
    with pytest.raises(ValueError):
        check_sentences_attachment(facts, draft)
