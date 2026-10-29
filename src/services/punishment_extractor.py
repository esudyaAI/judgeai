"""Adapter: operative part of a verdict -> ImposedSentence.

Regex only. A punishment that is clearly imposed ("в виде лишения свободы") but whose term
cannot be read is not guessed: its text window is returned for a separate LLM step.
"""

import re
from dataclasses import dataclass, field

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
)
from legal_core.precedents import QualificationCitation, qualification_citations

from src.services.russian_numerals import parse_russian_number

WINDOW_RADIUS = 200

_KINDS: list[tuple[PunishmentKind, str]] = [
    (PunishmentKind.LIFE_IMPRISONMENT, r"пожизненн\w+\s+лишени\w+\s+свободы"),
    (PunishmentKind.IMPRISONMENT, r"лишени\w+\s+свободы"),
    (PunishmentKind.DEPRIVATION_OF_RIGHT, r"лишени\w+\s+права"),
    (PunishmentKind.FINE, r"штраф\w*"),
    (PunishmentKind.COMPULSORY_WORKS, r"обязательн\w+\s+работ\w*"),
    (PunishmentKind.CORRECTIONAL_WORKS, r"исправительн\w+\s+работ\w*"),
    (PunishmentKind.FORCED_LABOUR, r"принудительн\w+\s+работ\w*"),
    (PunishmentKind.RESTRICTION_OF_FREEDOM, r"ограничени\w+\s+свободы"),
    (PunishmentKind.ARREST, r"арест\w*"),
]
_KIND_REGEX = re.compile(
    "|".join(f"(?P<k{i}>(?<![а-яё]){pattern})" for i, (_, pattern) in enumerate(_KINDS)),
    re.IGNORECASE,
)
_TERM_AFTER = re.compile(r"\s*(?:на\s+срок|сроком(?:\s+на)?|в\s+размере)\s+", re.IGNORECASE)
_TERM_STOP = re.compile(r"[,;.]|\s(?:с|со|условно|без|и|в)\s", re.IGNORECASE)
_EXPLICIT_IMPOSITION = re.compile(r"в\s+виде\s*$", re.IGNORECASE)
_TERM_BEFORE = re.compile(r"(?:в\s+виде|(?<![а-яё])к)\s+(?P<term>[^,;:]{1,60}?)\s*$", re.IGNORECASE)
_UNIT = re.compile(r"(?<![а-яё])(?P<unit>год\w*|лет|месяц\w*|час\w*)(?![а-яё])", re.IGNORECASE)
_PARENS = re.compile(r"\([^)]*\)")
_DIGITS = re.compile(r"\d[\d\s]*\d|\d")
_RUBLES = re.compile(
    r"(?P<num>\d[\d\s]*\d|\d)?\s*(?:\((?P<words>[^)]*)\))?\s*(?P<thousand>тыс\w*\.?)?\s*рубл",
    re.IGNORECASE,
)
# A dot ends a sentence unless it follows an initial ("К.") and the next word is capitalised.
_SENTENCE_END = re.compile(r"(?<![\s(][А-ЯЁ])\.\s+(?=[А-ЯЁ])|\n\s*\n")
_FINAL = re.compile(r"окончательн", re.IGNORECASE)
_AGGREGATION = re.compile(
    r"(?:ч\.\s*(?P<part>\d)\s*)?ст\.\s*(?P<article>69|70)(?!\d)", re.IGNORECASE
)
_CONDITIONAL = re.compile(
    r"ст\.\s*73(?!\d)|считать\s+условн|условн\w*\s+с\s+испытательн", re.IGNORECASE
)
_PROBATION = re.compile(r"испытательн\w+\s+срок\w*\s+(?:в\s+)?", re.IGNORECASE)


@dataclass(frozen=True)
class SentenceExtraction:
    sentence: ImposedSentence
    ambiguous_windows: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _Imposition:
    term: PunishmentTerm
    start: int
    end: int
    additional: bool
    final: bool
    kind_end: int


def parse_term(text: str) -> tuple[float | None, MeasureUnit | None]:
    """'2 (два) года 6 (шесть) месяцев' -> (30, months); '320 часов' -> (320, hours)."""
    total, unit, previous_end = 0.0, None, 0
    for match in _UNIT.finditer(text):
        number = _number_before(text[previous_end : match.start()])
        if number is None:
            return None, None
        word = match["unit"].lower()
        if word.startswith("час"):
            pair_unit, factor = MeasureUnit.HOURS, 1
        else:
            pair_unit, factor = MeasureUnit.MONTHS, (1 if word.startswith("месяц") else 12)
        if unit is not None and pair_unit is not unit:
            return None, None
        unit, total = pair_unit, total + number * factor
        previous_end = match.end()
    if unit is None or total <= 0:
        return None, None
    return (int(total) if float(total).is_integer() else total), unit


def _number_before(segment: str) -> float | None:
    plain = _PARENS.sub(" ", segment)
    digits = _DIGITS.findall(plain)
    if digits:
        return int(re.sub(r"\s", "", digits[-1]))
    words = re.findall(r"[а-яё]+", plain.lower())
    for size in range(min(4, len(words)), 0, -1):
        value = parse_russian_number(" ".join(words[-size:]))
        if value is not None:
            return value
    return None


def _parse_rubles(text: str) -> float | None:
    match = _RUBLES.search(text[:80])
    if not match:
        return None
    if match["num"]:
        value = int(re.sub(r"\s", "", match["num"]))
    elif match["words"]:
        value = parse_russian_number(match["words"])
    else:
        words = re.findall(r"[а-яё]+", text[: match.start("thousand") or match.end()].lower())
        value = None
        for size in range(min(4, len(words)), 0, -1):
            value = parse_russian_number(" ".join(words[-size:]))
            if value is not None:
                break
    if value is None:
        return None
    return value * 1000 if match["thousand"] else value


def _kind_of(match: re.Match) -> PunishmentKind:
    return next(_KINDS[int(n[1:])][0] for n, v in match.groupdict().items() if v)


def _sentence_bounds(text: str, position: int) -> tuple[int, int]:
    start = 0
    for end_match in _SENTENCE_END.finditer(text):
        if end_match.end() <= position:
            start = end_match.end()
        else:
            return start, end_match.start() + 1
    return start, len(text)


def _read_term(kind: PunishmentKind, after: str) -> PunishmentTerm | None:
    if kind is PunishmentKind.FINE:
        rubles = _parse_rubles(after)
        return PunishmentTerm(kind, rubles, MeasureUnit.RUBLES) if rubles else None
    stop = _TERM_STOP.search(after)
    amount, unit = parse_term(after[: stop.start()] if stop else after)
    return PunishmentTerm(kind, amount, unit) if amount else None


def _impositions(text: str) -> tuple[list[_Imposition], list[str]]:
    found, windows = [], []
    for match in _KIND_REGEX.finditer(text):
        kind = _kind_of(match)
        before = text[max(0, match.start() - 80) : match.start()]
        after_match = _TERM_AFTER.match(text, match.end())
        term = None
        end = match.end()
        if kind is PunishmentKind.LIFE_IMPRISONMENT:
            term = PunishmentTerm(kind)
        elif after_match:
            term = _read_term(kind, text[after_match.end() : after_match.end() + 120])
            end = after_match.end() + 40
        if term is None and kind is not PunishmentKind.FINE:
            before_match = _TERM_BEFORE.search(before)
            if before_match:
                amount, unit = parse_term(before_match["term"])
                if amount:
                    term = PunishmentTerm(kind, amount, unit)
        if term is None:
            if _EXPLICIT_IMPOSITION.search(before) or after_match:
                start = max(0, match.start() - WINDOW_RADIUS)
                windows.append(text[start : match.end() + WINDOW_RADIUS].strip())
            continue
        sentence_start, sentence_end = _sentence_bounds(text, match.start())
        additional = bool(re.search(r"(?:^|\s)(?:с|со)\s*$", before[-4:], re.IGNORECASE))
        final = bool(_FINAL.search(text[sentence_start : match.start()]))
        found.append(
            _Imposition(term, match.start(), min(end, sentence_end), additional, final, match.end())
        )
    return found, windows


def _reference_before(
    citations: tuple[QualificationCitation, ...], start: int, floor: int
) -> QualificationCitation | None:
    """Nearest criminal citation, sharing the card reader's code/part interpretation."""
    return next(
        (
            citation
            for citation in reversed(citations)
            if citation.start >= floor and citation.end <= start
        ),
        None,
    )


def extract_imposed_sentence(operative: str) -> SentenceExtraction:
    impositions, windows = _impositions(operative)
    citations = qualification_citations(operative)
    counts: list[CountSentence] = []
    final_term, final_quote, extra_final = None, "", []
    floor = 0
    for item in impositions:
        if item.final:
            if item.additional and final_term is not None:
                extra_final.append(item.term)
            elif final_term is None:
                final_term = item.term
                start, end = _sentence_bounds(operative, item.start)
                final_quote = operative[start:end].strip()
            continue
        if item.additional and counts:
            last = counts[-1]
            counts[-1] = CountSentence(
                last.qualification,
                last.reference,
                last.main,
                last.additional + (item.term,),
                last.quote,
            )
            continue
        found = _reference_before(citations, item.start, floor)
        reference, qualification, quote_start = None, "", item.start
        if found is not None:
            first = found.qualifications[0]
            reference = ArticleReference(first.article, first.part)
            qualification = operative[found.start : found.end].strip() + " УК РФ"
            quote_start = found.start
        counts.append(
            CountSentence(
                qualification,
                reference,
                item.term,
                (),
                operative[quote_start : item.end].strip(),
            )
        )
        # The next count's reference may start right after this term; the quote end (item.end)
        # can overshoot into it, so the search floor is the end of the punishment name.
        floor = item.kind_end
    aggregation = None
    if final_quote:
        rule = _AGGREGATION.search(final_quote)
        if rule:
            prefix = f"ч. {rule['part']} " if rule["part"] else ""
            aggregation = f"{prefix}ст. {rule['article']} УК РФ"
    probation = None
    probation_match = _PROBATION.search(operative)
    if probation_match:
        tail = operative[probation_match.end() : probation_match.end() + 60]
        stop = _TERM_STOP.search(tail)
        amount, unit = parse_term(tail[: stop.start()] if stop else tail)
        probation = int(amount) if unit is MeasureUnit.MONTHS else None
    sentence = ImposedSentence(
        counts=tuple(counts),
        final=final_term,
        aggregation_rule=aggregation,
        conditional=bool(_CONDITIONAL.search(operative)),
        probation_months=probation,
        final_quote=final_quote,
    )
    return SentenceExtraction(sentence, tuple(windows))
