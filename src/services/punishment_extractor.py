"""Adapter: operative part of a verdict -> ImposedSentence.

Regex only. A punishment that is clearly imposed ("в виде лишения свободы") but whose term
cannot be read is not guessed: its text window is returned for a separate LLM step.
"""

import re
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime

from legal_core.entities import (
    ArticleReference,
    CountSentence,
    FineCredit,
    ImposedSentence,
    MeasureUnit,
    PunishmentKind,
    PunishmentTerm,
    Unfinished,
)
from legal_core.precedents import QualificationCitation, qualification_citations

from src.services.defendant_blocks import defendant_names
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
# "на срок", "сроком на", and the typo "срок 8 лет" without the preposition
_TERM_AFTER = re.compile(r"[\s,]*(?:(?:на\s+)?срок(?:ом)?(?:\s+на)?|в\s+размере)\s+", re.IGNORECASE)
# "с лишением права заниматься деятельностью …, сроком на 2 года": the term trails the right
_TERM_AHEAD = re.compile(r"(?:на\s+срок|сроком(?:\s+на)?)\s+", re.IGNORECASE)
_TERM_AHEAD_REACH = 200
# The article-64 clause can interrupt the amount; never skip arbitrary prose or numbers.
_FINE_RULE_BRIDGE = (
    r"(?:с\s+применением\s+(?:ст\.|статьи)\s*64\b(?:\s+УК\s*РФ)?"
    r"|\(с\s+применением\s+(?:ст\.|статьи)\s*64\b[^()\n]{0,180}\))"
)
_FINE_AFTER = re.compile(
    r"[\s,]*(?:"
    + _FINE_RULE_BRIDGE
    + r"[\s,]*)?(?:(?:в\s+доход\s+государства|в\s+определ\w*\s+денежн\w*\s+сумм\w*)[\s,]*)?"
    r"в\s+(?:размере|сумме)\s+",
    re.IGNORECASE,
)
# an amount removed when the verdict was published: "в размере сумма", "<данные изъяты> часов"
_HIDDEN_AMOUNT = re.compile(r"\s*(?:сумма(?![а-яё])|<[^>]{0,20}>|№(?!\s*\d))", re.IGNORECASE)
# "наказание - 220 часов обязательных работ", "назначить ДВА года ШЕСТЬ месяцев лишения свободы"
_TERM_BEFORE_PREFIX = re.compile(
    r"(?:в\s+виде|(?<![а-яё])к|наказани\w*\s*[-–—:]|назначить)\s+", re.IGNORECASE
)
_DIRECT_TERM_BEFORE = re.compile(
    r"(?<![\w.])(?P<term>(?:\d+(?:[.,]\d+)?(?:\s*\([^()]{1,40}\))?\s+"
    r"(?:лет|год[а-яё]*|месяц[а-яё]*|час(?:а|ов)?|день|дня|дней)\s*){1,3})$",
    re.IGNORECASE,
)
_TERM_STOP = re.compile(r"[,;.]|\s(?:с|со|условно|без|и|в)\s", re.IGNORECASE)
_EXPLICIT_IMPOSITION = re.compile(r"в\s+виде\s*$", re.IGNORECASE)
_UNIT = re.compile(
    r"(?<![а-яё])(?P<unit>год\w*|лет|месяц\w*|час(?:а|ов|у|ам|ами|ах)?|день|дня|дней)(?![а-яё])",
    re.IGNORECASE,
)
_PARENS = re.compile(r"\([^)]*\)")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)?(?:\s+\d{3})*")
_RUBLES = re.compile(
    r"(?P<num>\d{1,3}(?:[\s.]\d{3})+|\d+)?\s*(?:[(/](?P<words>[^)/]*)[)/])?\s*"
    r"(?P<thousand>тыс\w*\.?)?\s*руб(?:л|\.|(?![а-яё]))",
    re.IGNORECASE,
)

# A dot ends a sentence unless it follows an initial ("К.") and the next word is capitalised.
_SENTENCE_END = re.compile(r"(?<![\s(][А-ЯЁ])\.\s+(?=[А-ЯЁ])|\n\s*\n")
# The aggregate sentence. "окончательно назначить" outranks an earlier "по совокупности …
# назначить": an aggregate by ч. 3 ст. 69 may be followed by the final one by ст. 70.
_FINALLY = re.compile(r"окончательн", re.IGNORECASE)
_AGGREGATE = re.compile(
    r"по\s+совокупности|(?:на\s+основании|в\s+соответствии\s+с|с\s+применением)\s+"
    r"(?:ч\.\s*\d\s*)?ст\.\s*(?:69|70)(?!\d)",
    re.IGNORECASE,
)
# A punishment named but not imposed here: restrictions of ч. 1 ст. 53 "на период назначенного
# ему наказания в виде …", its supervision and execution, an unserved term joined under ст. 70.
_NOT_IMPOSED_BEFORE = re.compile(
    r"(?:назначенного\s+(?:ему\s+|ей\s+)?наказани|надзор|неотбыт|срок\w*\s+отбывани|исчисл"
    r"|зачесть|зачет)[^.;]*$",
    re.IGNORECASE,
)
_NOT_IMPOSED_AFTER = re.compile(r"^[^.;]{0,20}?присоедин", re.IGNORECASE)
# ч. 1 ст. 30 (preparation) or ч. 3 ст. 30 (attempt) right before the count's article.
_UNFINISHED = re.compile(
    r"(?:ч\.?\s*|част\w*\s+)(?P<part>[13])\s*,?\s*(?:ст\.?|стать\w*)\s*30(?![\d.])",
    re.IGNORECASE,
)
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
    final: int  # 0 — a count, 1 — an aggregate "по совокупности", 2 — "окончательно"
    kind_end: int


def parse_term(text: str) -> tuple[float | None, MeasureUnit | None]:
    """'2 (два) года 6 (шесть) месяцев' -> (30, months); '320 часов' -> (320, hours)."""
    total, unit, previous_end = 0.0, None, 0
    for match in _UNIT.finditer(text):
        number = _number_before(text[previous_end : match.start()])
        if number is None:
            return None, None
        word = match["unit"].lower()
        if word in ("день", "дня", "дней"):
            pair_unit, factor = MeasureUnit.DAYS, 1
        elif word.startswith("час"):
            pair_unit, factor = MeasureUnit.HOURS, 1
        else:
            pair_unit, factor = MeasureUnit.MONTHS, (1 if word.startswith("месяц") else 12)
        if unit is not None and pair_unit is not unit:
            if {unit, pair_unit} == {MeasureUnit.DAYS, MeasureUnit.MONTHS}:
                total = total * 30 if unit is MeasureUnit.MONTHS else total
                number = number * factor * 30 if pair_unit is MeasureUnit.MONTHS else number
                pair_unit, factor = MeasureUnit.DAYS, 1
            else:
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
        return float(re.sub(r"\s", "", digits[-1]).replace(",", "."))
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
    if (match["num"] or match["words"]) and text[: match.start()].strip():
        return None
    if match["num"]:
        value = int(re.sub(r"[\s.]", "", match["num"]))
    elif match["words"]:
        value = parse_russian_number(match["words"])
    else:
        words = re.findall(r"[а-яё]+", text[: match.start("thousand") or match.end()].lower())
        value = parse_russian_number(" ".join(words))
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
    # A publication placeholder is authoritative: later monetary amounts are not this term.
    if _HIDDEN_AMOUNT.match(after):
        return PunishmentTerm(kind)
    if kind is PunishmentKind.FINE:
        rubles = _parse_rubles(after)
        if rubles:
            return PunishmentTerm(kind, rubles, MeasureUnit.RUBLES)
    else:
        stop = _TERM_STOP.search(after)
        amount, unit = parse_term(after[: stop.start()] if stop else after)
        if amount:
            return PunishmentTerm(kind, amount, unit)
    # The kind is known even when publication removed the amount; nothing is left to resolve.
    return PunishmentTerm(kind) if _HIDDEN_AMOUNT.match(after) else None


def _term_before(before: str) -> tuple[float | None, MeasureUnit | None]:
    """The term written ahead of the kind, after the nearest "в виде", "к", "наказание -"."""
    direct = _DIRECT_TERM_BEFORE.search(before)
    if direct:
        return parse_term(direct["term"])
    prefixes = deque(_TERM_BEFORE_PREFIX.finditer(before), maxlen=1)
    if not prefixes:
        return None, None
    term = before[prefixes[0].end() :].strip()
    if not term or len(term) > 60 or re.search(r"[,;:]", term):
        return None, None
    return parse_term(term)


def _trailing_term(kind: PunishmentKind, text: str, start: int) -> PunishmentTerm | None:
    """Term after the description of a right, within the sentence and before any other kind."""
    _, sentence_end = _sentence_bounds(text, start)
    ahead = _TERM_AHEAD.search(text, start, min(sentence_end, start + _TERM_AHEAD_REACH))
    if ahead is None or _KIND_REGEX.search(text, start, ahead.start()):
        return None
    return _read_term(kind, text[ahead.end() : ahead.end() + 120])


def _impositions(text: str) -> tuple[list[_Imposition], list[str]]:
    found, windows = [], []
    for match in _KIND_REGEX.finditer(text):
        kind = _kind_of(match)
        before = text[max(0, match.start() - 80) : match.start()]
        if _NOT_IMPOSED_BEFORE.search(text[max(0, match.start() - 90) : match.start()]) or (
            _NOT_IMPOSED_AFTER.match(text, match.end(), match.end() + 40)
        ):
            continue
        # A credit decision is not another imposed punishment or an LLM window.
        if kind is PunishmentKind.FINE:
            local_start, local_end = _sentence_bounds(text, match.start())
            local = text[local_start:local_end]
            prefix = text[local_start : match.start()]
            rule = _CREDIT_RULE.search(local)
            imposition = list(re.finditer(r"назначить|признать|признан\w*", prefix, re.I))
            new_imposition = bool(
                imposition
                and (
                    not rule or rule.start() > len(prefix) or imposition[-1].start() > rule.start()
                )
            )
            if rule and _CREDIT_ACTION.search(local) and not new_imposition:
                continue
        after_match = _TERM_AFTER.match(text, match.end())
        if after_match is None and kind is PunishmentKind.FINE:
            after_match = _FINE_AFTER.match(text, match.end())
        term = None
        end = match.end()
        additional = bool(re.search(r"(?:^|\s)(?:с|со)\s*$", before[-4:], re.IGNORECASE))
        if kind is PunishmentKind.LIFE_IMPRISONMENT:
            term = PunishmentTerm(kind)
        elif after_match:
            term = _read_term(kind, text[after_match.end() : after_match.end() + 120])
            end = after_match.end() + 40
        if term is None and additional and kind is PunishmentKind.DEPRIVATION_OF_RIGHT:
            term = _trailing_term(kind, text, match.end())
        # The words before an additional punishment are the main one's term, never its own.
        if term is None and kind is not PunishmentKind.FINE and not additional:
            amount, unit = _term_before(before)
            if amount:
                term = PunishmentTerm(kind, amount, unit)
        if term is None:
            if _EXPLICIT_IMPOSITION.search(before) or after_match:
                start = max(0, match.start() - WINDOW_RADIUS)
                windows.append(text[start : match.end() + WINDOW_RADIUS].strip())
            continue
        sentence_start, sentence_end = _sentence_bounds(text, match.start())
        prefix = text[sentence_start : match.start()]
        final = 2 if _FINALLY.search(prefix) else 1 if _AGGREGATE.search(prefix) else 0
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


def _rule(quote: str) -> str | None:
    match = _AGGREGATION.search(quote)
    if match:
        return (f"ч. {match['part']} " if match["part"] else "") + f"ст. {match['article']} УК РФ"
    return None


def _stated_term(statement: str) -> PunishmentTerm | None:
    kind_match = _KIND_REGEX.search(statement)
    if kind_match is None:
        return None
    kind = _kind_of(kind_match)
    after = statement[kind_match.end() :]
    marker = _TERM_AFTER.match(after)
    term = _read_term(kind, after[marker.end() :] if marker else after)
    if term is None and kind is not PunishmentKind.FINE:
        amount, unit = parse_term(statement[max(0, kind_match.start() - 100) : kind_match.start()])
        if amount:
            term = PunishmentTerm(kind, amount, unit)
    return term


def _date(value: str):
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        return None


def read_chronology(text: str):
    matches = list(
        re.finditer(
            r"(?:прежн\w*\s+приговор\w*|перв\w*\s+приговор\w*|приговор\w*\s+по\s+первому\s+делу)\s+от\s+(\d{2}\.\d{2}\.\d{4})",
            text,
            re.I,
        )
    )
    dates = {_date(m[1]) for m in matches}
    prior = next(iter(dates)) if len(dates) == 1 else None
    prior_quote = matches[0][0] if prior else ""
    credits = []
    for statement in re.split(r"\n\s*\n|(?<=[.;])\s+(?=[А-ЯЁ])", text):
        if re.search(r"зачесть[^.;]{0,80}отбыт|отбыто[^.;]{0,80}зачесть", statement, re.I):
            term = _stated_term(statement)
            if term:
                credits.append((term, statement.strip()))
    return (
        prior,
        prior_quote,
        credits[0][0] if len(credits) == 1 else None,
        credits[0][1] if len(credits) == 1 else "",
    )


def read_prior_terms(text: str):
    balances, joins = [], []
    for statement in re.split(r"\n\s*\n|(?<=[.;])\s+(?=[А-ЯЁ])", text):
        if not re.search(r"неотбыт|присоедин", statement, re.I):
            continue
        term = _stated_term(statement)
        if term is None:
            continue
        if re.search(r"присоедин", statement, re.I):
            # Joined part is not the entire unserved balance.
            joins.append((term, statement.strip()))
        elif re.search(r"неотбыт", statement, re.I):
            balances.append((term, statement.strip()))
    balance_terms = {term for term, _ in balances}
    join_terms = {term for term, _ in joins}
    balance = balances[0] if len(balance_terms) == 1 else (None, "")
    joined = joins[0] if len(join_terms) == 1 else (None, "")
    return *balance, *joined


_CREDIT_RULE = re.compile(r"ч(?:асть|асти|\.)?\s*5\s*ст(?:атьи|атья|\.)?\s*72\b", re.I)
_CREDIT_ACTION = re.compile(r"(?:смягчить|снизить|уменьшить|полностью\s+освободить)", re.I)
_CREDIT_NEGATIVE = re.compile(
    r"просил\w*|просит|предложил\w*|предлагал\w*|ходатайств\w*|отказать|"
    r"не\s+(?:находит|считает|имеется|усматривает|подлежит|может)|нет\s+оснований|"
    r"не\s+(?:смягч\w*|сниз\w*|уменьш\w*|освобод\w*)",
    re.I,
)


def _fine_credits(text: str, impositions: list[_Imposition]) -> tuple[FineCredit, ...]:
    """Attach only explicit credit decisions with unambiguous local targets."""
    result = []
    indexed = []
    index = 0
    for event in impositions:
        if event.additional:
            continue
        indexed.append((event, None if event.final else index))
        if not event.final:
            index += 1
    for action in _CREDIT_ACTION.finditer(text):
        start, end = _sentence_bounds(text, action.start())
        quote = text[start:end].strip()
        if not _CREDIT_RULE.search(quote) or _CREDIT_NEGATIVE.search(quote):
            continue
        release = action.group().lower().startswith("полностью")
        if release and not re.search(r"от\s+отбывания[^\n]{0,100}штраф", quote, re.I):
            continue
        prior = [(e, n) for e, n in indexed if e.start < action.start()]
        event, number = prior[-1] if prior else (None, None)
        fine = event is not None and event.term.kind is PunishmentKind.FINE
        line_start = text.rfind("\n", 0, action.start()) + 1
        local = text[line_start:end]
        if not fine and not re.search(r"штраф", local, re.I):
            continue
        same_line = event is not None and text.rfind("\n", 0, event.start) == text.rfind(
            "\n", 0, action.start()
        )
        target = bool(fine and (event.final or len(prior) == 1 or same_line))
        if event and event.final and any(e.final and e.start > event.start for e, _ in indexed):
            target = False
        # A qualification explicitly named in a credit is not the latest aggregate by default.
        qualifications = qualification_citations(quote)
        if qualifications:
            target = False
        people = set(re.findall(r"ФИО\s*\d+", quote, re.I))
        names = defendant_names(text[: event.start]) if event else []
        earlier_people = {names[-1].upper()} if names else set()
        if people and not {p.upper() for p in people}.issubset(earlier_people):
            target = False
        named_people = re.findall(
            r"[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ][а-яё-]+"
            r"|[А-ЯЁ][а-яё-]+[ \t]+(?:[А-ЯЁ]\.[ \t]*){1,2}"
            r"|(?:[А-ЯЁ]\.[ \t]*){3}",
            quote,
        )
        for person in named_people:
            words = person.lower().split()
            known = names[-1].split() if names else []
            if (
                len(words) != 3
                or len(known) != 3
                or not all(
                    left.startswith(right[:-2] if len(right) > 4 else right)
                    for left, right in zip(words, known, strict=True)
                )
            ):
                target = False
        tail = text[action.end() : end]
        amount_match = re.search(r"\bдо\s+", tail, re.I)
        if re.search(
            r"издерж|расход|гражданск|рассроч|ежемесяч",
            tail[: amount_match.start()] if amount_match else tail,
            re.I,
        ):
            continue
        amount = _parse_rubles(tail[amount_match.end() :]) if amount_match else None
        if not release and amount_match is None:
            continue
        original = event.term.amount if target else None
        status = (
            "stated"
            if target
            and original is not None
            and (release or amount is not None and 0 < amount <= original)
            else "requires_review"
        )
        result.append(
            FineCredit(
                "final" if target and event.final else "count" if target else "unassigned",
                number if target and not event.final else None,
                original,
                None if release else amount,
                release,
                status,
                quote,
            )
        )
    # Multiple decisions for one target require a human to establish their sequence.
    for i, credit in enumerate(result):
        if sum(c.scope == credit.scope and c.count_index == credit.count_index for c in result) > 1:
            result[i] = replace(credit, status="requires_review")
    return tuple(result)


def extract_imposed_sentence(operative: str, description: str = "") -> SentenceExtraction:
    impositions, windows = _impositions(operative)
    citations = qualification_citations(operative)
    counts: list[CountSentence] = []
    final_term, final_quote, extra_final, final_rank = None, "", [], 0
    floor = 0
    intermediate, intermediate_rule, intermediate_quote = None, None, ""
    for item in impositions:
        if item.final:
            if item.additional and final_term is not None:
                if item.final == final_rank:
                    extra_final.append(item.term)
            else:
                start, end = _sentence_bounds(operative, item.start)
                quote = operative[start:end].strip()
                rule = _rule(quote)
                if final_term is None or item.final >= final_rank or (rule and "70" in rule):
                    if final_term is not None and _rule(final_quote) and "69" in _rule(final_quote):
                        intermediate, intermediate_rule, intermediate_quote = (
                            final_term,
                            _rule(final_quote),
                            final_quote,
                        )
                    final_term, final_rank, extra_final = item.term, item.final, []
                    final_quote = quote
            continue
        if item.additional and counts:
            counts[-1] = replace(counts[-1], additional=counts[-1].additional + (item.term,))
            continue
        found = _reference_before(citations, item.start, floor)
        reference, qualification, quote_start, unfinished = None, "", item.start, None
        conflict = False
        if found is not None:
            first = found.qualifications[0]
            reference = ArticleReference(first.article, first.part)
            qualification = operative[found.start : found.end].strip() + " УК РФ"
            quote_start = found.start
            last = deque(
                _UNFINISHED.finditer(operative, max(floor, found.start - 30), found.start),
                maxlen=1,
            )
            stage = last[0] if last else None
            if stage is not None:
                unfinished = Unfinished.ATTEMPT if stage["part"] == "3" else Unfinished.PREPARATION
                qualification = f"ч. {stage['part']} ст. 30, {qualification}"
        sentence_start, _ = _sentence_bounds(operative, item.start)
        context = operative[max(floor, sentence_start) : item.start]
        words = set()
        if re.search(r"(?<!неоконченное )покушени\w*\s+на", context, re.I):
            words.add(Unfinished.ATTEMPT)
        if re.search(r"приготовлени\w*\s+к", context, re.I):
            words.add(Unfinished.PREPARATION)
        if words:
            conflict = len(words) > 1 or (unfinished is not None and unfinished not in words)
            if not conflict:
                unfinished = next(iter(words))
            quote_start = max(floor, sentence_start)
        counts.append(
            CountSentence(
                qualification,
                reference,
                item.term,
                (),
                operative[quote_start : item.end].strip(),
                unfinished,
                conflict,
            )
        )
        # The next count's reference may start right after this term; the quote end (item.end)
        # can overshoot into it, so the search floor is the end of the punishment name.
        floor = item.kind_end
    if description:
        for index, count in enumerate(counts):
            if count.reference is None:
                continue
            stages = set()
            offence_dates = []
            for statement in re.split(r"\n\s*\n|(?<=[.;])\s+(?=[А-ЯЁ])", description):
                references = {
                    ArticleReference(q.article, q.part)
                    for citation in qualification_citations(statement)
                    for q in citation.qualifications
                }
                if (
                    references == {count.reference}
                    and sum(c.reference == count.reference for c in counts) == 1
                ):
                    dated = re.search(
                        r"соверш(?:ил\w*|ен\w*|ён\w*)[^.;]{0,50}?(\d{2}\.\d{2}\.\d{4})",
                        statement,
                        re.I,
                    )
                    if dated:
                        offence_dates.append((_date(dated[1]), statement))
                if references != {count.reference} or re.search(r"\bне\b", statement, re.I):
                    continue
                if re.search(r"покушени\w*\s+на", statement, re.I):
                    stages.add(Unfinished.ATTEMPT)
                if re.search(r"приготовлени\w*\s+к", statement, re.I):
                    stages.add(Unfinished.PREPARATION)
            if offence_dates:
                unique_dates = {d for d, _ in offence_dates}
                dated = offence_dates[0] if len(unique_dates) == 1 else (None, "")
                counts[index] = replace(
                    counts[index], offence_date=dated[0], offence_date_quote=dated[1]
                )
            if stages:
                ambiguous = sum(c.reference == count.reference for c in counts) > 1
                conflict = (
                    count.stage_conflict
                    or ambiguous
                    or len(stages) > 1
                    or (count.unfinished is not None and count.unfinished not in stages)
                )
                counts[index] = replace(
                    counts[index],
                    stage_conflict=conflict,
                    unfinished=count.unfinished if conflict else next(iter(stages)),
                )
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
    unserved, unserved_quote, joined, joined_quote = read_prior_terms(operative)
    prior, prior_quote, credited, credited_quote = read_chronology(description + "\n" + operative)
    sentence = ImposedSentence(
        counts=tuple(counts),
        final=final_term,
        aggregation_rule=aggregation,
        conditional=bool(_CONDITIONAL.search(operative)),
        probation_months=probation,
        final_quote=final_quote,
        intermediate=intermediate,
        intermediate_rule=intermediate_rule,
        intermediate_quote=intermediate_quote,
        unserved=unserved,
        unserved_quote=unserved_quote,
        joined=joined,
        joined_quote=joined_quote,
        final_additional=tuple(extra_final),
        prior_judgment_date=prior,
        prior_judgment_quote=prior_quote,
        credited=credited,
        credited_quote=credited_quote,
        fine_credits=_fine_credits(operative, impositions),
    )
    return SentenceExtraction(sentence, tuple(windows))
