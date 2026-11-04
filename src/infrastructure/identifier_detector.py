"""Local span detector for common identifiers; not a completeness claim for arbitrary PII.

Unlike the existing embedding normalizer, this adapter preserves original coordinates and
text, so citations can be restored locally without sending a correspondence table.
"""

import re

from src.domain.privacy import IdentifierSpan

_NAME = r"(?:[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?|[А-ЯЁ]{2,}(?:-[А-ЯЁ]+)?)"
_PATRONYMIC = (
    r"(?:[А-ЯЁ][а-яё]*(?:ович|евич|ич|овна|евна|ична)"
    r"|[А-ЯЁ]+(?:ОВИЧ|ЕВИЧ|ИЧ|ОВНА|ЕВНА|ИЧНА))"
)
_LATIN = r"(?:[A-Z][a-z]+(?:[-\'][A-Z][a-z]+)?|[A-Z]{2,}(?:-[A-Z]+)?)"
_MONTHS = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
_NAME_PATTERNS = (
    # Full names, including the given-name/patronymic/surname order.
    re.compile(rf"\b{_NAME}\s+{_NAME}\s+{_PATRONYMIC}\b"),
    re.compile(rf"\b{_NAME}\s+{_PATRONYMIC}\s+{_NAME}\b"),
    re.compile(rf"\b{_NAME}\s+[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.)?"),
    re.compile(rf"(?<!\w)[А-ЯЁ]\.\s*(?:[А-ЯЁ]\.\s*)?{_NAME}\b"),
    re.compile(
        rf"(?i:\b(?:подсудим\w*|обвиняем\w*|осужд[её]нн\w*|потерпевш\w*|свидетел\w*|"
        rf"гражданин\w*|гражданк\w*|защитник\w*))\s+(?P<identifier>{_NAME}(?:\s+{_NAME})?)\b"
    ),
    re.compile(
        rf"(?i:\b(?:defendant|victim|witness|подсудим\w*|обвиняем\w*|свидетел\w*))"
        rf"\s+(?P<identifier>{_LATIN}(?:\s+{_LATIN}){{0,2}})\b"
    ),
)
_PATTERNS = (
    # Contacts and long numeric identifiers (SNILS, passport, INN, cards/accounts).
    re.compile(r"(?<![\w@])[\w.+%-]+@[\w.-]+\.[a-zA-Zа-яА-Я]{2,}(?!\w)"),
    re.compile(r"(?<!\d)(?:\+7|8)[\s(.-]*\d{3}[\s).\-]*\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}\s?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{4}\s+\d{6}(?!\d)"),
    re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{10,20}(?!\d)"),
    re.compile(r"(?i:\bVIN\s*[:№]?\s*)(?P<identifier>[A-HJ-NPR-Z0-9]{17})\b"),
    re.compile(
        r"(?<!\w)[АВЕКМНОРСТУХABEKMHOPCTYX]\d{3}[АВЕКМНОРСТУХABEKMHOPCTYX]{2}\s?\d{2,3}(?!\w)"
    ),
    re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){9,14}(?!\d)"),
    re.compile(r"(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)"),
    # Dates can identify a person. Legal calculations continue to use the local original.
    re.compile(r"(?<!\d)\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}(?!\d)"),
    re.compile(rf"(?<!\d)\d{{1,2}}\s+(?:{_MONTHS})\s+(?:19|20)\d{{2}}(?:\s*г(?:ода|\.)?)?", re.I),
    re.compile(
        r"(?i:\b(?:адрес\w*\s*[:—-]|прожива\w*\s+по\s+адресу|зарегистрирова\w*\s+по\s+адресу))\s*(?P<identifier>[^;\n]{3,250})"
    ),
    re.compile(rf"(?i:\b(?:ул\.|улица|проспект|пр-т|переулок|пер\.))\s*{_NAME}[^;\n]{{0,100}}"),
    re.compile(rf"(?i:\b(?:г\.|город))\s*{_NAME}"),
    re.compile(r"https?://[^\s<>\"]+", re.I),
    # Escape any literal token in untrusted input before the model can echo it back.
    re.compile(r"\[JAI_[a-f0-9]{32}_\d+\]"),
)


def detect_identifiers(text: str) -> tuple[IdentifierSpan, ...]:
    spans = []
    for pattern in (*_NAME_PATTERNS, *_PATTERNS):
        for match in pattern.finditer(text):
            start, end = (
                match.span("identifier") if "identifier" in match.re.groupindex else match.span()
            )
            spans.append(IdentifierSpan(start, end))
            if pattern in _NAME_PATTERNS:
                # Known name components/stems also protect later standalone and declined
                # mentions. This is a heuristic, not a complete Russian name recognizer.
                for word in re.finditer(rf"(?:{_NAME}|{_LATIN})", text[start:end]):
                    begin, finish = start + word.start(), start + word.end()
                    spans.append(IdentifierSpan(begin, finish))
                    if finish - begin > 3 and text[finish - 1].lower() in "аяй":
                        spans.append(IdentifierSpan(begin, finish - 1))
    return tuple(spans)
