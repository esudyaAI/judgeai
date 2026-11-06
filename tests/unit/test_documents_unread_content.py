"""T17.4: pure policy for document parts that were present but not read."""

import pytest

from src.domain.documents import ExtractedDocument, reading_warnings, with_unread_content


def document(status="ok", issues=()):
    return ExtractedDocument("Текст", 1, status, issues)


def test_no_unread_content_keeps_the_document():
    original = document()
    assert with_unread_content(original, set()) is original


@pytest.mark.parametrize("found", [{"pdf_attachments"}, {"xfa_form"}, {"pdf_portfolio"}])
def test_complete_reading_becomes_partial(found):
    result = with_unread_content(document(), found)
    assert (result.status, result.issues, result.text) == ("partial", tuple(found), "Текст")


def test_issues_are_appended_in_a_fixed_order_without_duplicates():
    result = with_unread_content(
        document("partial", ("no_text_layer", "xfa_form")), {"xfa_form", "pdf_attachments"}
    )
    assert result.issues == ("no_text_layer", "xfa_form", "pdf_attachments")


def test_portfolio_subsumes_its_attachments():
    result = with_unread_content(document(), {"pdf_attachments", "pdf_portfolio", "xfa_form"})
    assert result.issues == ("pdf_portfolio", "xfa_form")


@pytest.mark.parametrize("status", ["empty", "error", "partial"])
def test_other_statuses_are_not_upgraded(status):
    assert with_unread_content(document(status), {"pdf_attachments"}).status == status


def test_unknown_issue_is_a_programming_error():
    with pytest.raises(ValueError):
        with_unread_content(document(), {"macros"})


def test_every_unread_content_issue_has_a_russian_warning():
    result = with_unread_content(document(), {"pdf_attachments", "xfa_form"})
    warnings = reading_warnings(result)
    assert len(warnings) == 2
    assert all(any("а" <= char <= "я" for char in warning) for warning in warnings)
    portfolio = reading_warnings(with_unread_content(document(), {"pdf_portfolio"}))
    assert "портфел" in portfolio[0]
