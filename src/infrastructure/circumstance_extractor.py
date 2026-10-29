"""Adapter: circumstances, recidivism and applied General Part rules from a verdict, by regex.

Circumstances are scoped to clauses labelled «смягчающ…» / «отягчающ…», including
preposed facts and explicit lists. Negation affects its clause, not unrelated findings.
Party requests alone are not court findings.
Every code keeps the sentence it was read from.
"""

import re
from dataclasses import dataclass, field

from legal_core.precedents import Recidivism

EXTRACTOR_VERSION = "circumstances/2"

_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+(?=[А-ЯЁ])|\n\s*\n")
_NEGATION = re.compile(
    r"\bне\s+(?:усматрива|находит|име[её]т|имеется|установлен|применя|подлеж|признаёт|признает)"
    r"|отсутству|нет\s+оснований|оснований\s+для[^.]{0,120}\bнет\b|не\s+установил|без\s+применени",
    re.IGNORECASE,
)
_MARKER = re.compile(r"(?P<kind>смягчающ|отягчающ)\w*", re.IGNORECASE)
_EXPLICIT = re.compile(
    r'(?:п(?:\.\s*п)?\.\s*[«"“]?(?P<points>[а-яё](?:\s*,\s*[а-яё])*)[»"”)]?\s*)?'
    r"ч\.\s*(?P<part>\d(?:\.\d)?)\s*ст\.\s*(?P<article>6[13])(?!\d)",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"\s*;\s*|,\s*(?=(?:а(?!\s+также\b)|но|однако|при\s+этом)\b)", re.I)
_PARTY_REQUEST = re.compile(
    r"(?:защитник|адвокат|подсудим\w*|осужденн\w*|осуждённ\w*)[^.;]{0,100}"
    r"(?:просит|просил|полагает|считает|предлагает|заявляет)",
    re.I,
)
_COURT_FINDING = re.compile(r"\bсуд\s+(?:призна[её]т|признал|учитывает|установил|считает)", re.I)
_MITIGATING_WORDS: list[tuple[str, re.Pattern]] = [
    ("61.1.и", re.compile(r"явк\w*\s+с\s+повинной|активн\w+\s+способствовани", re.I)),
    ("61.1.г", re.compile(r"малолетн\w+\s+(?:ребенка|ребёнка|детей|дочер|сын)", re.I)),
    ("61.1.в", re.compile(r"беременност", re.I)),
    (
        "61.1.к",
        re.compile(r"возмещени\w+\s+(?:\w+\s+)?(?:ущерба|вреда)|возместил|заглаживани", re.I),
    ),
    ("61.2", re.compile(r"признани\w+\s+вины|раскаяни|состояни\w+\s+здоровья", re.I)),
]
_AGGRAVATING_WORDS: list[tuple[str, re.Pattern]] = [
    ("63.1.а", re.compile(r"рецидив", re.I)),
    ("63.1.в", re.compile(r"групп\w+\s+лиц", re.I)),
    ("63.1.1", re.compile(r"состояни\w+\s+(?:алкогольного\s+)?опьянени", re.I)),
]
_GENERAL_RULES = re.compile(
    r"(?:ч\.\s*(?P<part>\d)\s*)?ст\.\s*(?P<article>62|64|68|73)(?!\d)", re.IGNORECASE
)
_RECIDIVISM: list[tuple[Recidivism, re.Pattern]] = [
    (
        Recidivism.ESPECIALLY_DANGEROUS,
        re.compile(r"особо\s+опасн\w*\s+рецидив|рецидив[^.;]{0,50}особо\s+опасн", re.I),
    ),
    (
        Recidivism.DANGEROUS,
        re.compile(r"(?<!особо\s)опасн\w*\s+рецидив|рецидив[^.;]{0,50}\bопасн\w*", re.I),
    ),
    (Recidivism.SIMPLE, re.compile(r"рецидив", re.I)),
]
_NOT_CONVICTED = re.compile(
    r"(?<![а-яё])не\s*суд[иі]м\w*|не\s+имеющ\w+\s+судимост|судимост\w*\s+не\s+имеет",
    re.I,
)
_NO_RECIDIVISM = re.compile(
    r"рецидив[^.;]{0,100}(?:отсутству|не\s+(?:установлен|образу|имеется))"
    r"|не\s+(?:образу\w*|установлен\w*)[^.;]{0,60}рецидив",
    re.I,
)


@dataclass
class CircumstanceReading:
    mitigating: dict[str, str] = field(default_factory=dict)
    aggravating: dict[str, str] = field(default_factory=dict)
    applied_general: dict[str, str] = field(default_factory=dict)
    recidivism: Recidivism | None = None
    recidivism_quote: str = ""


def circumstance_statements(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def _explicit_codes(segment: str, article: str) -> list[str]:
    codes = []
    for match in _EXPLICIT.finditer(segment):
        if match["article"] != article:
            continue
        points = re.findall(r"[а-яё]", (match["points"] or "").lower())
        base = f"{article}.{match['part']}"
        if points:
            codes.extend(f"{base}.{p}" for p in points)
        else:
            codes.append(base)
    return codes


def _is_finding(clause: str) -> bool:
    return not _PARTY_REQUEST.search(clause) or bool(_COURT_FINDING.search(clause))


def _read_segment(segment: str, mitigating: bool, quote: str, reading: CircumstanceReading) -> None:
    if _NEGATION.search(segment) or not _is_finding(segment):
        return
    article = "61" if mitigating else "63"
    target = reading.mitigating if mitigating else reading.aggravating
    words = _MITIGATING_WORDS if mitigating else _AGGRAVATING_WORDS
    codes = _explicit_codes(segment, article)
    codes += [code for code, pattern in words if pattern.search(segment)]
    for code in codes:
        target.setdefault(code, quote)


def _read_circumstances(sentence: str, reading: CircumstanceReading) -> None:
    list_kind = None
    for clause in _CLAUSE_SPLIT.split(sentence):
        markers = list(_MARKER.finditer(clause))
        if markers:
            # A fact can precede its label: "наличие детей суд признаёт смягчающим".
            kinds = {m["kind"].lower().startswith("смягч") for m in markers}
            if len(kinds) == 1:
                kind = kinds.pop()
                _read_segment(clause, kind, sentence, reading)
                list_kind = (
                    kind
                    if ":" in clause and not _NEGATION.search(clause) and _is_finding(clause)
                    else None
                )
            else:
                list_kind = None
                for index, marker in enumerate(markers):
                    start = 0 if index == 0 else marker.start()
                    end = markers[index + 1].start() if index + 1 < len(markers) else len(clause)
                    _read_segment(
                        clause[start:end],
                        marker["kind"].lower().startswith("смягч"),
                        sentence,
                        reading,
                    )
        elif list_kind is not None:
            _read_segment(clause, list_kind, sentence, reading)


def extract_circumstances(
    description: str, operative: str = "", introduction: str = ""
) -> CircumstanceReading:
    reading = CircumstanceReading()
    for sentence in circumstance_statements(description):
        _read_circumstances(sentence, reading)
    recidivism_quotes = {}
    no_recidivism_quote = ""
    for sentence in circumstance_statements(f"{description}\n\n{operative}"):
        for clause in _CLAUSE_SPLIT.split(sentence):
            if not _is_finding(clause):
                continue
            no_recidivism = _NO_RECIDIVISM.search(clause)
            if no_recidivism and not re.search(r"опасн", clause[: no_recidivism.start()], re.I):
                no_recidivism_quote = no_recidivism_quote or sentence
            if _NEGATION.search(clause):
                continue
            for match in _GENERAL_RULES.finditer(clause):
                article, part = match["article"], match["part"]
                if article in ("62", "68") and part is None:
                    continue
                code = f"{article}.{part}" if article in ("62", "68") else article
                reading.applied_general.setdefault(code, sentence)
            for kind, pattern in _RECIDIVISM:
                if kind is not Recidivism.SIMPLE and re.search(r"\bне\b", clause, re.I):
                    continue
                if not no_recidivism and pattern.search(clause):
                    recidivism_quotes.setdefault(kind, sentence)
                    break
    if recidivism_quotes and not no_recidivism_quote:
        # A later precise degree refines an earlier generic mention, not vice versa.
        reading.recidivism = next(kind for kind, _ in _RECIDIVISM if kind in recidivism_quotes)
        reading.recidivism_quote = recidivism_quotes[reading.recidivism]
    elif not recidivism_quotes:
        person = f"{introduction}\n\n{description}"
        quote = no_recidivism_quote or next(
            (s for s in circumstance_statements(person) if _NOT_CONVICTED.search(s)), None
        )
        if quote:
            reading.recidivism, reading.recidivism_quote = Recidivism.NONE, quote
    return reading
