"""T45.3 — «what does the law provide for this qualification?» answered from the law base.

A question such as «какая санкция по ч. 2 ст. 158» or «что грозит по ч. 1 ст. 105» is read
into one qualification; the answer lists the punishment alternatives of that part exactly as
the newest imported edition of УК РФ in the database states them, with the edition, its URL
and whether a lawyer has reviewed it. No bound is written by code or by a model: a part the
base has not parsed is said to be not parsed, and conflicting editions are not chosen between.

A question that asks for statistics («средний срок…») is a practice question (T45.1), never
this one. A point of a part has the sanction of its part: in УК РФ sanctions are per part.
"""

import re
from dataclasses import dataclass

from legal_core.entities import MeasureUnit, SanctionRole, StatutorySanction
from legal_core.precedents import Qualification, parse_qualifications

from src.domain.practice_facts import asks_statistics, format_months
from src.domain.punishment_names import PUNISHMENT_NAMES

_SANCTION = re.compile(
    r"(?<![а-яё])(?:санкци|предусм|грозит|наказываетс|по\s+закону)", re.IGNORECASE
)

VERIFIED = "verified"


@dataclass(frozen=True)
class SanctionQuestion:
    """«Which punishments does the statute provide for this qualification?»"""

    qualification: Qualification

    @property
    def target(self) -> Qualification:
        """The part (or the article without parts) whose sanction answers the question."""
        asked = self.qualification
        return Qualification(asked.article, asked.part)


def parse_sanction_question(text: str) -> SanctionQuestion | None:
    if asks_statistics(text) or not _SANCTION.search(text):
        return None
    qualifications = parse_qualifications(text)
    if len(qualifications) != 1:
        return None
    return SanctionQuestion(qualifications[0])


@dataclass(frozen=True)
class SanctionSource:
    """Where the sanction was read: the imported edition of the statute in the database."""

    edition_label: str
    source_url: str
    provision_locator: str
    verification_status: str


@dataclass(frozen=True)
class SanctionFacts:
    question: SanctionQuestion
    sanctions: tuple[StatutorySanction, ...]  # empty — the part is not parsed in the base
    source: SanctionSource | None
    conflict: bool = False  # editions of the article contradict each other: none is chosen


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
    by_part: dict[int | None, list[StatutorySanction]] = {}
    for sanction in facts.sanctions:
        by_part.setdefault(sanction.part, []).append(sanction)
    parts = sorted(by_part, key=lambda part: (part is not None, part or 0))
    lines = ["Санкция по базе законов (как в тексте редакции):"]
    lines += [_part_line(part, target.article, by_part[part]) for part in parts]
    if asked.point is not None:
        lines.append(f"Для п. «{asked.point}» действует санкция всей части.")
    return "\n".join(lines)


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
