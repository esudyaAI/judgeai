"""Synthetic identifiers; no source case material or real external requests."""

import pytest

from src.application.anonymization import anonymize_texts
from src.infrastructure.identifier_detector import detect_identifiers


@pytest.mark.parametrize(
    "identifier",
    [
        "Иванов Иван Иванович",
        "Defendant John Smith",
        "+44 7911 123456",
        "1990-02-01",
        "Иван Иванович Иванов",
        "Иванова Ольга Петровна",
        "Иванов И.И.",
        "И. И. Иванов",
        "+7 (999) 123-45-67",
        "89991234567",
        "test.person@example.invalid",
        "123-456-789 00",
        "1234 567890",
        "123456789012",
        "1234 5678 9012 3456",
        "12345678901234567890",
        "А123ВС777",
        "01.02.1990",
        "1 февраля 1990 года",
        "https://private.invalid/cases/123?name=synthetic",
    ],
)
def test_common_identifier_is_masked_and_restored(identifier):
    text = f"Материал: {identifier}; конец."
    result = anonymize_texts((text,), detect_identifiers, "a" * 32)
    assert identifier not in result.texts[0]
    assert result.session.restore(result.texts[0]) == text


def test_role_name_is_propagated_to_other_occurrences_and_other_messages():
    texts = ("Подсудимый Иванов пояснил.", "Иванов признал вину; адрес: ул. Примерная, д. 10;")
    result = anonymize_texts(texts, detect_identifiers, "b" * 32)
    assert all("Иванов" not in value for value in result.texts)
    assert "Примерная" not in result.texts[1]
    assert tuple(result.session.restore(t) for t in result.texts) == texts


def test_legal_references_and_punishment_units_are_preserved():
    text = "По ч. 2 ст. 158 УК РФ назначить 1 год 6 месяцев лишения свободы и штраф 100 000 рублей."
    assert anonymize_texts((text,), detect_identifiers, "c" * 32).texts == (text,)


def test_known_name_parts_are_hidden_in_uppercase_and_declined_mentions():
    source = (
        "Подсудимый Иванов Иван Иванович; потерпевшая Иванова Ольга Петровна; "
        "ИВАНОВУ передали сообщение от Ольги."
    )
    result = anonymize_texts((source,), detect_identifiers, "d" * 32)
    assert "ИВАНОВ" not in result.texts[0]
    assert "Ольг" not in result.texts[0]
    assert result.session.restore(result.texts[0]) == source
