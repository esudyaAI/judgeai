"""T45.7 — «к какой категории относится ч. 2 ст. 158?» answered by code from the law base.

The category of a crime (ст. 15 УК РФ) follows from the form of guilt and the most severe main
punishment of the part. That punishment is read from the sanctions of the newest imported
edition of the article in the database (as in T45.3), and the category is computed by the art. 15
rule of legal_core: no category is stored as data or written by a model. The form of guilt is
never inferred from the article number: when the question does not name it and the two forms
give different categories, both are stated. A part the base has not parsed is said to be not
parsed, and conflicting editions are not chosen between.

T45.10 — a category question that names a date («к какой категории относилась ч. 2 ст. 158 на
01.03.2020») is still answered from the newest edition only, so, as for a sanction (T45.9), the
date is compared with the period of force of the provision in the base: not in force on it — no
category is given; otherwise the category comes with a code-written note on what the code did
not check — the period (unknown, or not one exact date), the applicability of the edition to the
offence (ст. 9–10 УК РФ) and the edition of ст. 15 itself, which the rule is written by.
"""

import re
from dataclasses import dataclass
from datetime import date

from legal_core.entities import Category, Guilt, PunishmentKind, SanctionRole, StatutorySanction
from legal_core.precedents import Qualification, parse_qualifications
from legal_core.rules.art15 import SOURCE as ART15_SOURCE
from legal_core.rules.art15 import categorize
from legal_core.rules.sanction_ceiling import sanction_ceiling_for_part

from src.domain.norm_period import describe_period, in_force_on
from src.domain.practice_facts import asks_statistics, format_months
from src.domain.punishment_names import PUNISHMENT_NAMES
from src.domain.sanction_facts import (
    AskedDate,
    SanctionFacts,
    SanctionQuestion,
    SanctionSource,
    asked_date,
    asks_category,
    describe_sanction_source,
)

_INTENT = re.compile(r"(?<![а-яё])умышленн", re.IGNORECASE)
_NEGLIGENCE = re.compile(r"(?<![а-яё])неосторожн", re.IGNORECASE)

CATEGORY_LABELS = {
    Category.SMALL: "преступление небольшой тяжести",
    Category.MEDIUM: "преступление средней тяжести",
    Category.GRAVE: "тяжкое преступление",
    Category.ESPECIALLY_GRAVE: "особо тяжкое преступление",
}
_GUILT_WORDS = {Guilt.INTENTIONAL: "умышленное", Guilt.NEGLIGENT: "по неосторожности"}
_HARSHER = (PunishmentKind.LIFE_IMPRISONMENT, PunishmentKind.DEATH_PENALTY)


@dataclass(frozen=True)
class CategoryQuestion:
    """«Which category of art. 15 is this qualification?» — guilt only when the question
    names it."""

    qualification: Qualification
    guilt: Guilt | None = None
    asked: AskedDate | None = None  # T45.10: the date the question names, if any

    @property
    def target(self) -> Qualification:
        """The part (or the article without parts) whose sanction decides the category."""
        asked = self.qualification
        return Qualification(asked.article, asked.part)


def _named_guilt(text: str) -> Guilt | None:
    intent, negligence = bool(_INTENT.search(text)), bool(_NEGLIGENCE.search(text))
    if intent == negligence:  # neither, or both («умышленное или по неосторожности?»)
        return None
    return Guilt.INTENTIONAL if intent else Guilt.NEGLIGENT


def parse_category_question(text: str) -> CategoryQuestion | None:
    if asks_statistics(text) or not asks_category(text):
        return None
    qualifications = parse_qualifications(text)
    if len(qualifications) != 1:
        return None
    return CategoryQuestion(qualifications[0], _named_guilt(text), asked_date(text))


@dataclass(frozen=True)
class CategoryFacts:
    question: CategoryQuestion
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


@dataclass(frozen=True)
class PartCategory:
    """The category of one part by each form of guilt; None — art. 15 gives none (or no data)."""

    part: int | None
    ceiling: str | None  # the most severe main punishment in words; None — no main sanction
    categories: tuple[tuple[Guilt, Category | None], ...]


def _category(guilt: Guilt, ceiling) -> Category | None:
    try:
        return categorize(guilt, ceiling)
    except ValueError:  # ч. 4 ст. 15 ends at 15 years for a negligent crime
        return None


def _ceiling_words(sanctions: list[StatutorySanction], ceiling) -> str:
    if ceiling.harsher_than_imprisonment:
        kinds = [
            PUNISHMENT_NAMES[s.kind]
            for s in sanctions
            if s.role is SanctionRole.MAIN and s.kind in _HARSHER
        ]
        return "в санкции есть " + " и ".join(dict.fromkeys(kinds))
    if ceiling.max_imprisonment_months is None:
        return "лишения свободы среди основных наказаний санкции нет"
    return f"наибольший срок лишения свободы — {format_months(ceiling.max_imprisonment_months)}"


def part_categories(facts: CategoryFacts) -> list[PartCategory]:
    """Every part of the reading in order, with the category art. 15 gives it by guilt."""
    by_part: dict[int | None, list[StatutorySanction]] = {}
    for sanction in facts.sanctions:
        by_part.setdefault(sanction.part, []).append(sanction)
    asked_guilt = facts.question.guilt
    guilts = (asked_guilt,) if asked_guilt is not None else (Guilt.INTENTIONAL, Guilt.NEGLIGENT)
    result = []
    for part in sorted(by_part, key=lambda part: (part is not None, part or 0)):
        ceiling = sanction_ceiling_for_part(by_part[part], part)
        if ceiling is None:
            result.append(PartCategory(part, None, tuple((g, None) for g in guilts)))
            continue
        result.append(
            PartCategory(
                part,
                _ceiling_words(by_part[part], ceiling),
                tuple((g, _category(g, ceiling)) for g in guilts),
            )
        )
    return result


def _label(category: Category | None) -> str:
    return CATEGORY_LABELS[category] if category is not None else "ст. 15 категории не определяет"


def _categories_words(item: PartCategory, *, guilt_asked: bool) -> str:
    if guilt_asked:
        guilt, category = item.categories[0]
        return f"{_label(category)} ({_GUILT_WORDS[guilt]})"
    values = {category for _, category in item.categories}
    if len(values) == 1:
        return f"{_label(values.pop())} при любой форме вины"
    return "; ".join(
        f"если {_GUILT_WORDS[guilt]} — {_label(category)}" for guilt, category in item.categories
    )


def depends_on_guilt(item: PartCategory) -> bool:
    return len({category for _, category in item.categories}) > 1


def describe_category_facts(facts: CategoryFacts) -> str:
    """The answer in words: the category computed by code from the sanction read from the base."""
    asked = facts.question.qualification
    target = facts.question.target
    if facts.conflict:
        return (
            f"Конфликт справочных данных по {target}: в базе законов противоречащие редакции "
            "статьи, ни одна не выбрана — категорию определить нельзя."
        )
    if not facts.sanctions:
        return f"В базе законов санкция {target} не разобрана: категорию определить нельзя."
    if facts.in_force is False:
        source = facts.source
        period = describe_period(source.effective_from, source.effective_to)
        return (
            f"На {facts.on:%d.%m.%Y} положение {source.provision_locator} новейшей редакции "
            f"в базе законов, из которого прочитана санкция {target}, не действовало (период "
            f"действия в базе: {period}). Редакцию на эту дату программа не выбирает — "
            "категорию определить нельзя."
        )
    guilt_asked = facts.question.guilt is not None
    items = part_categories(facts)
    lines = [
        "Категория по ст. 15 УК РФ — по наибольшему основному наказанию санкции из базы законов:"
    ]
    for item in items:
        where = Qualification(target.article, item.part)
        if item.ceiling is None:
            lines.append(
                f"{where}: основные наказания санкции не разобраны — категорию определить нельзя."
            )
            continue
        lines.append(
            f"{where}: {item.ceiling}; {_categories_words(item, guilt_asked=guilt_asked)}."
        )
    if not guilt_asked and any(depends_on_guilt(item) for item in items):
        lines.append(
            "Категория зависит от формы вины: в вопросе она не названа, а по номеру статьи "
            "программа её не определяет."
        )
    if asked.point is not None:
        lines.append(f"Для п. «{asked.point}» действует санкция всей части.")
    return "\n".join(lines)


_ART15_EDITION = (
    "Правило ст. 15 программа применяет в одной редакции (текст указан в источнике); "
    "действовала ли эта редакция ст. 15 на нужную дату, программа не проверяла."
)


def describe_category_date_note(facts: CategoryFacts) -> str:
    """T45.10 — what the code did not check about the date of the question; written by code.

    Empty without a date, when no category was given, or when the refusal already says it.
    """
    asked = facts.question.asked
    if asked is None or facts.conflict or not facts.sanctions or facts.in_force is False:
        return ""
    if asked.unclear:
        head = (
            "В вопросе не одна точная дата (год, несколько дат или несуществующая дата): "
            "категория определена по санкции новейшей редакции в базе законов, действовала "
            "ли она на нужную дату, программа не проверяла."
        )
    elif facts.in_force is None:
        head = (
            "Период действия положения в базе законов не задан: действовала ли санкция, по "
            f"которой определена категория, на {asked.on:%d.%m.%Y}, программа не подтверждает."
        )
    else:
        source = facts.source
        period = describe_period(source.effective_from, source.effective_to)
        head = (
            f"По периоду действия в базе законов ({period}) положение с санкцией действовало "
            f"на {asked.on:%d.%m.%Y}; применима ли эта редакция к деянию (ст. 9–10 УК РФ), "
            "программа не оценивала."
        )
    return f"{head}\n{_ART15_EDITION}"


def describe_category_source(facts: CategoryFacts) -> str:
    """The edition the sanction was read from and the text the art. 15 rule was written by."""
    sanction_source = describe_sanction_source(
        SanctionFacts(SanctionQuestion(facts.question.qualification), facts.sanctions, facts.source)
    )
    if not sanction_source:
        return ""
    return (
        f"{sanction_source}\n"
        "Категорию считает правило программы по ст. 15 УК РФ, написанное по тексту: "
        f"{ART15_SOURCE}."
    )
