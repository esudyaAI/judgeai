"""T45.3 — «what does the law provide for this qualification?» answered from the law base.

A question such as «какая санкция по ч. 2 ст. 158» or «что грозит по ч. 1 ст. 105» is read
into one qualification; the answer lists the punishment alternatives of that part exactly as
the newest imported edition of УК РФ in the database states them, with the edition, its URL
and whether a lawyer has reviewed it. No bound is written by code or by a model: a part the
base has not parsed is said to be not parsed, and conflicting editions are not chosen between.

A question that asks for statistics («средний срок…») is a practice question (T45.1), and one
that asks for the category («к какой категории относится…») is a category question (T45.7),
never this one. A point of a part has the sanction of its part: in УК РФ sanctions are per part.

T45.9 — a question that names a date («какая санкция по ч. 2 ст. 158 на 01.03.2020») is still
answered from the newest edition only, so the code compares the date with the period of force
of the provision in the base: not in force on it — no sanction is given; period unknown, or a
year / several dates instead of one date — the sanction is given with a note that the date was
not confirmed. Whether that edition applies to the offence (ст. 9–10 УК РФ) is not judged here.
"""

import re
from dataclasses import dataclass
from datetime import date

from legal_core.entities import MeasureUnit, SanctionRole, StatutorySanction
from legal_core.precedents import Qualification, parse_qualifications

from src.domain.norm_period import describe_period, in_force_on
from src.domain.practice_facts import asks_statistics, format_months
from src.domain.punishment_names import PUNISHMENT_NAMES

_SANCTION = re.compile(
    r"(?<![а-яё])(?:санкци|предусм|грози[тл]|наказываетс|по\s+закону)", re.IGNORECASE
)

VERIFIED = "verified"
# T45.7: the category of a crime (ст. 15). «Тяжесть» only with «преступление» or «степень»:
# «вред средней тяжести» in a sanction question is the harm of ст. 112, not a category.
_CATEGORY = re.compile(
    r"(?<![а-яё])(?:категори|тяжест\w*\s+преступлени|степен\w*\s+тяжест)", re.IGNORECASE
)


def asks_category(text: str) -> bool:
    """The question asks for the category of a crime (T45.7), not for its sanction."""
    return bool(_CATEGORY.search(text))


_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "января",
            "февраля",
            "марта",
            "апреля",
            "мая",
            "июня",
            "июля",
            "августа",
            "сентября",
            "октября",
            "ноября",
            "декабря",
        ),
        start=1,
    )
}
_NUMERIC_DATE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])")
_WORDED_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})(?!\d)", re.IGNORECASE
)
_YEAR = re.compile(r"(?<![\d.])(?:1[89]|20)\d{2}(?![\d.])\s*(?:г\.|год)", re.IGNORECASE)


@dataclass(frozen=True)
class AskedDate:
    """The date a question names: `on` — exactly one real date; otherwise it is unclear."""

    on: date | None

    @property
    def unclear(self) -> bool:
        return self.on is None


def asked_date(text: str) -> AskedDate | None:
    """None — no date in the question; AskedDate(None) — a year, several dates or a non-date."""
    found: set[date] = set()
    impossible = False
    numeric = [(d, m, y) for d, m, y in _NUMERIC_DATE.findall(text)]
    worded = [(d, _MONTHS[m.lower()], y) for d, m, y in _WORDED_DATE.findall(text)]
    for day, month, year in numeric + worded:
        try:
            found.add(date(int(year), int(month), int(day)))
        except ValueError:
            impossible = True
    rest = _WORDED_DATE.sub(" ", _NUMERIC_DATE.sub(" ", text))
    year_only = bool(_YEAR.search(rest))
    if len(found) == 1 and not impossible and not year_only:
        return AskedDate(next(iter(found)))
    if found or impossible or year_only:
        return AskedDate(None)
    return None


@dataclass(frozen=True)
class SanctionQuestion:
    """«Which punishments does the statute provide for this qualification?»"""

    qualification: Qualification
    asked: AskedDate | None = None  # T45.9: the date the question names, if any

    @property
    def target(self) -> Qualification:
        """The part (or the article without parts) whose sanction answers the question."""
        asked = self.qualification
        return Qualification(asked.article, asked.part)


def parse_sanction_question(text: str) -> SanctionQuestion | None:
    if asks_statistics(text) or asks_category(text) or not _SANCTION.search(text):
        return None
    qualifications = parse_qualifications(text)
    if len(qualifications) != 1:
        return None
    return SanctionQuestion(qualifications[0], asked_date(text))


@dataclass(frozen=True)
class SanctionSource:
    """Where the sanction was read: the imported edition of the statute in the database."""

    edition_label: str
    source_url: str
    provision_locator: str
    verification_status: str
    effective_from: date | None = None  # T45.9: period of force of the provision in the base
    effective_to: date | None = None


@dataclass(frozen=True)
class SanctionFacts:
    question: SanctionQuestion
    sanctions: tuple[StatutorySanction, ...]  # empty — the part is not parsed in the base
    source: SanctionSource | None
    conflict: bool = False  # editions of the article contradict each other: none is chosen

    @property
    def on(self) -> date | None:
        asked = self.question.asked
        return asked.on if asked is not None else None

    @property
    def in_force(self) -> bool | None:
        """The provision read was in force on the asked date; None — no date or not known."""
        if self.on is None or self.source is None or not self.sanctions or self.conflict:
            return None
        return in_force_on(self.source.effective_from, self.source.effective_to, self.on)


def _amount(value: float, unit: MeasureUnit) -> str:
    if unit is MeasureUnit.MONTHS:
        return format_months(value)
    number = f"{int(value):,}".replace(",", " ") if value == int(value) else f"{value:g}"
    number = number.replace(".", ",", 1)
    if unit is MeasureUnit.RUBLES:
        return f"{number} ₽"
    if unit is MeasureUnit.HOURS:
        return f"{number} ч."
    return f"{number} дн."


def describe_alternative(sanction: StatutorySanction) -> str:
    """«лишение свободы от 2 г. до 6 г.» — the bounds as the statute gives them."""
    name = PUNISHMENT_NAMES[sanction.kind]
    if sanction.unit is None:
        return name
    bounds = []
    if sanction.min_value:
        bounds.append(f"от {_amount(sanction.min_value, sanction.unit)}")
    if sanction.max_value:
        bounds.append(f"до {_amount(sanction.max_value, sanction.unit)}")
    return " ".join([name, *bounds])


def _part_line(part: int | None, article: str, sanctions: list[StatutorySanction]) -> str:
    def listed(role: SanctionRole) -> str:
        found = [describe_alternative(s) for s in sanctions if s.role is role]
        return "; ".join(dict.fromkeys(found))

    line = f"{Qualification(article, part)}: основные наказания — "
    line += listed(SanctionRole.MAIN) or "в разборе нет"
    additional = listed(SanctionRole.ADDITIONAL)
    if additional:
        line += f"; дополнительные — {additional}"
    # Bounds end with an abbreviation dot («1 г.»): the sentence does not get a second one.
    return line if line.endswith(".") else line + "."


def describe_sanction_facts(facts: SanctionFacts) -> str:
    """The answer in words; every bound in it is a value of the sanctions read from the base."""
    asked = facts.question.qualification
    target = facts.question.target
    if facts.conflict:
        return (
            f"Конфликт справочных данных по {target}: в базе законов противоречащие редакции "
            "статьи, ни одна не выбрана — ответ дать нельзя."
        )
    if not facts.sanctions:
        return f"В базе законов санкция {target} не разобрана: ответ дать нельзя."
    if facts.in_force is False:
        source = facts.source
        period = describe_period(source.effective_from, source.effective_to)
        return (
            f"На {facts.on:%d.%m.%Y} положение {source.provision_locator} новейшей редакции "
            f"в базе законов, из которого прочитана санкция {target}, не действовало (период "
            f"действия в базе: {period}). Редакцию на эту дату программа не выбирает — "
            "ответ дать нельзя."
        )
    by_part: dict[int | None, list[StatutorySanction]] = {}
    for sanction in facts.sanctions:
        by_part.setdefault(sanction.part, []).append(sanction)
    parts = sorted(by_part, key=lambda part: (part is not None, part or 0))
    lines = ["Санкция по базе законов (как в тексте редакции):"]
    lines += [_part_line(part, target.article, by_part[part]) for part in parts]
    if asked.point is not None:
        lines.append(f"Для п. «{asked.point}» действует санкция всей части.")
    return "\n".join(lines)


def describe_date_note(facts: SanctionFacts) -> str:
    """T45.9 — what the code knows about the date of the question; written by code, not a model.

    Empty without a date, when no sanction was given, or when the refusal already says it.
    """
    asked = facts.question.asked
    if asked is None or facts.conflict or not facts.sanctions or facts.in_force is False:
        return ""
    if asked.unclear:
        return (
            "В вопросе не одна точная дата (год, несколько дат или несуществующая дата): "
            "санкция дана по новейшей редакции в базе законов, действовала ли она на нужную "
            "дату, программа не проверяла."
        )
    on = f"{asked.on:%d.%m.%Y}"
    if facts.in_force is None:
        return (
            "Период действия положения в базе законов не задан: действовала ли эта санкция "
            f"на {on}, программа не подтверждает."
        )
    source = facts.source
    period = describe_period(source.effective_from, source.effective_to)
    return (
        f"По периоду действия в базе законов ({period}) положение действовало на {on}; "
        "применима ли эта редакция к деянию (ст. 9–10 УК РФ), программа не оценивала."
    )


def describe_sanction_source(facts: SanctionFacts) -> str:
    """«Источник: …» — the edition the sanction was read from; empty when nothing was read."""
    source = facts.source
    if source is None or not facts.sanctions:
        return ""
    review = (
        "сверена юристом"
        if source.verification_status == VERIFIED
        else f"не сверена юристом (статус: {source.verification_status})"
    )
    return (
        f"Источник: {source.edition_label}, {source.source_url}, "
        f"положение {source.provision_locator}; редакция {review}."
    )
