"""T45.1 — factual questions about practice answered by code, not by a language model.

A question such as «средний срок по ч. 4 ст. 159» is read into one qualification; the
numbers are counted here over precedent cards of the practice base, and every number comes
with the verdicts it was counted from (court, date, URL, УИД). A question without a
statistics word, without a qualification or with several of them is not a factual question
for this module (None): it is never guessed and never handed to a model to answer.

Comparability is the rule of the practice comparison (T28, src/application/practice_report):
a verdict is counted when exactly one of its counts carries the asked qualification; the term
is that count's own one, and the final term only when the verdict has a single count. The
aggregate term of several counts is never attributed to one of them. A verdict with several
matching counts is ambiguous: it is excluded and the exclusion is reported, not hidden.
Statistics are those of legal_core.rules.practice_comparison; with fewer than its minimum of
terms no mean, median or range is stated: a handful of verdicts is not practice.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from legal_core.precedents import PrecedentCard, Qualification, parse_qualifications
from legal_core.rules.practice_comparison import PracticeComparison, compare_with_practice

_STATISTIC = re.compile(
    r"(?<![а-яё])(?:средн|медиан|типичн|обычн|разброс|диапазон|квартил|статистик)",
    re.IGNORECASE,
)
_TERM = re.compile(
    r"(?<![а-яё])(?:срок|наказани|лишени\w*\s+свобод|дают|назнача|сажа)", re.IGNORECASE
)


@dataclass(frozen=True)
class PracticeTermQuestion:
    """«Which imprisonment terms are imposed for this qualification in the practice base?»"""

    qualification: Qualification


def parse_practice_term_question(text: str) -> PracticeTermQuestion | None:
    if not _STATISTIC.search(text) or not _TERM.search(text):
        return None
    qualifications = parse_qualifications(text)
    if len(qualifications) != 1:
        return None
    return PracticeTermQuestion(qualifications[0])


def covers(asked: Qualification, actual: Qualification) -> bool:
    """A question by part covers every point of that part; by article — every part."""
    if asked.article != actual.article:
        return False
    if asked.part is not None and asked.part != actual.part:
        return False
    return asked.point is None or asked.point == actual.point


@dataclass(frozen=True)
class PracticeVerdict:
    """A precedent card of the practice base with the origin of its verdict."""

    card_id: int
    card: PrecedentCard
    court_name: str | None
    decision_date: date | None
    source_url: str | None
    uid: str | None


@dataclass(frozen=True)
class CountedVerdict:
    card_id: int
    court_name: str | None
    decision_date: date | None
    source_url: str | None
    uid: str | None
    months: float | None  # imprisonment term of the matching count; None — unknown or milder
    conditional: bool


@dataclass(frozen=True)
class PracticeTermFacts:
    question: PracticeTermQuestion
    found: int  # verdicts with the asked qualification in any count
    excluded: int  # of them, with several matching counts: no term of one count
    counted: tuple[CountedVerdict, ...]
    mean_months: float | None
    comparison: PracticeComparison

    @property
    def enough_data(self) -> bool:
        return self.comparison.enough_data


def _single_count(card: PrecedentCard, asked: Qualification) -> PrecedentCard | None:
    matches = [e for e in card.episodes if covers(asked, e.qualification)]
    if len(matches) != 1:
        return None
    match = matches[0]
    term = match.punishment
    if term is None and len(card.episodes) == 1:
        term = card.final
    return replace(card, episodes=(replace(match, punishment=term),), final=None)


def practice_term_facts(
    question: PracticeTermQuestion, verdicts: Sequence[PracticeVerdict]
) -> PracticeTermFacts:
    asked = question.qualification
    found = [v for v in verdicts if any(covers(asked, e.qualification) for e in v.card.episodes)]
    cards: list[PrecedentCard] = []
    counted: list[CountedVerdict] = []
    for item in found:
        single = _single_count(item.card, asked)
        if single is None:
            continue
        cards.append(single)
        counted.append(
            CountedVerdict(
                item.card_id,
                item.court_name,
                item.decision_date,
                item.source_url,
                item.uid,
                single.imprisonment_months,
                single.conditional,
            )
        )
    terms = [c.months for c in counted if c.months is not None]
    mean = round(sum(terms) / len(terms), 4) if terms else None
    return PracticeTermFacts(
        question=question,
        found=len(found),
        excluded=len(found) - len(counted),
        counted=tuple(counted),
        mean_months=mean,
        comparison=compare_with_practice(cards, None),
    )


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _verdicts(n: int) -> str:
    return f"{n} {_plural(n, 'приговор', 'приговора', 'приговоров')}"


def format_months(value: float) -> str:
    """Whole months as years and months; a fraction of a month (days) with one decimal."""
    if value != int(value):
        return f"{round(value, 1):g} мес.".replace(".", ",", 1)
    years, rest = divmod(int(value), 12)
    parts = ([f"{years} г."] if years else []) + ([f"{rest} мес."] if rest else [])
    return " ".join(parts) or "0 мес."


def describe_practice_term_facts(facts: PracticeTermFacts) -> str:
    """The answer in words; every number in it is one of the facts counted above."""
    asked = str(facts.question.qualification)
    if facts.found == 0:
        return f"В базе практики нет приговоров по {asked}: ответ по практике дать нельзя."
    counted = len(facts.counted)
    head = f"По {asked} в базе практики {_verdicts(facts.found)}, учтено {counted}"
    if facts.excluded:
        word = "исключён" if facts.excluded == 1 else "исключено"
        head += f", {word} {facts.excluded}"
        head += " (статья вменена по нескольким эпизодам, срок за один эпизод не выделен)"
    comparison = facts.comparison
    if not facts.enough_data:
        return (
            f"{head}. Срок лишения свободы известен в {comparison.with_term} из {counted} — "
            "этого недостаточно, чтобы говорить о практике, поэтому статистика не считается. "
            "Приговоры приведены в источниках."
        )
    share = comparison.conditional_share or 0
    return (
        f"{head}. Срок лишения свободы известен в {comparison.with_term} из {counted}: "
        f"среднее {format_months(facts.mean_months)}, "
        f"медиана {format_months(comparison.median_months)}, "
        f"от {format_months(comparison.min_months)} до {format_months(comparison.max_months)}, "
        f"половина сроков — от {format_months(comparison.p25_months)} "
        f"до {format_months(comparison.p75_months)}; условно — {round(share * 100)}% учтённых. "
        "Цифры посчитаны кодом по карточкам приговоров, источники приведены."
    )
