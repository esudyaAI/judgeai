"""Precedent cards: a verdict reduced to the facts that make two cases comparable.

The card is built from a verdict text by adapters (regex first, LLM only for windows) and is
the same structure for the user's draft (the query) and for verdicts in the practice base.
Nothing here depends on storage, HTTP or a language model.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from legal_core.entities import MeasureUnit, PunishmentKind, PunishmentTerm

# Articles 1-104 form the General Part of УК РФ and are never a qualification of a count.
FIRST_SPECIAL_PART_ARTICLE = 105

# Codes of circumstances: '61.1.и' (п. «и» ч. 1 ст. 61), '61.2', '63.1.а', '63.1.1'.
_CIRCUMSTANCE_CODE = re.compile(r"^6[13]\.\d(?:\.\d{1,2})?(?:\.[а-я])?$")
# Codes of applied General Part rules: '62.1', '64', '68.3', '73'.
_GENERAL_RULE_CODE = re.compile(r"^\d{2}(?:\.\d)?$")


class Recidivism(StrEnum):
    """Kind of recidivism (art. 18 УК РФ); an unknown kind is None on the card, not a value."""

    NONE = "none"
    SIMPLE = "simple"
    DANGEROUS = "dangerous"
    ESPECIALLY_DANGEROUS = "especially_dangerous"


@dataclass(frozen=True)
class Qualification:
    """Article, part and point of the Special Part, e.g. п. «в» ч. 2 ст. 158 -> key '158/2/в'.

    The key separator is '/', because article numbers themselves contain dots (228.1).
    """

    article: str
    part: int | None = None
    point: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", self.article):
            raise ValueError(f"invalid article number: {self.article!r}")
        if int(self.article.split(".")[0]) < FIRST_SPECIAL_PART_ARTICLE:
            raise ValueError("a qualification refers to the Special Part of УК РФ")
        if self.part is not None and self.part <= 0:
            raise ValueError("part must be positive")
        if self.point is not None and not re.fullmatch(r"[а-яё]", self.point):
            raise ValueError("point is a single Cyrillic letter")

    @property
    def key(self) -> str:
        return "/".join(str(x) for x in (self.article, self.part, self.point) if x is not None)

    def __str__(self) -> str:
        point = f"п. «{self.point}» " if self.point else ""
        part = f"ч. {self.part} " if self.part is not None else ""
        return f"{point}{part}ст. {self.article} УК РФ"


_QUALIFICATION = re.compile(
    r"(?:(?:п\.\s*(?:п\.\s*)?|пункт\w*\s+)«(?P<points>[а-яё,\s]{1,20})»\s*)?"
    r"(?:(?:ч\.|част\w*)\s*(?P<part>\d{1,2})\s+)?(?:ст\.|стать\w*)\s*"
    r"(?P<article>\d{1,3}(?:\.\d{1,2})?)(?!\d)",
    re.IGNORECASE,
)
_OTHER_CODE = re.compile(r"\b(?:УПК|КоАП|ГК|ГПК|АПК)\b")


def parse_qualifications(text: str) -> tuple[Qualification, ...]:
    """All Special Part qualifications in a text, in order, without duplicates.

    'п.п. «в, г» ч. 2 ст. 158' expands to two qualifications. Texts citing another code are
    ignored as a whole, so 'ст. 307 УПК РФ' is never read as an article of УК РФ.
    """
    if not text or _OTHER_CODE.search(text):
        return ()
    found: list[Qualification] = []
    for match in _QUALIFICATION.finditer(text):
        if int(match["article"].split(".")[0]) < FIRST_SPECIAL_PART_ARTICLE:
            continue
        part = int(match["part"]) if match["part"] else None
        points = re.findall(r"[а-яё]", (match["points"] or "").lower()) or [None]
        for point in points:
            qualification = Qualification(match["article"], part, point)
            if qualification not in found:
                found.append(qualification)
    return tuple(found)


@dataclass(frozen=True)
class PrecedentEpisode:
    """One count of a verdict: its qualification and the punishment imposed for it."""

    qualification: Qualification
    punishment: PunishmentTerm | None = None


@dataclass(frozen=True)
class PrecedentCard:
    """Comparable facts of one verdict. recidivism None means the verdict does not say."""

    episodes: tuple[PrecedentEpisode, ...]
    mitigating: frozenset[str]
    aggravating: frozenset[str]
    recidivism: Recidivism | None
    applied_general: frozenset[str]
    final: PunishmentTerm | None
    conditional: bool
    fabula: str

    def __post_init__(self) -> None:
        for code in self.mitigating | self.aggravating:
            if not _CIRCUMSTANCE_CODE.match(code):
                raise ValueError(f"invalid circumstance code: {code!r}")
        for code in self.applied_general:
            if not _GENERAL_RULE_CODE.match(code):
                raise ValueError(f"invalid General Part rule code: {code!r}")

    @property
    def main_qualification(self) -> Qualification | None:
        return self.episodes[0].qualification if self.episodes else None

    @property
    def qualification_keys(self) -> frozenset[str]:
        return frozenset(e.qualification.key for e in self.episodes)

    @property
    def punishment(self) -> PunishmentTerm | None:
        """Final punishment, or the single count's one when there is no aggregate; any kind."""
        if self.final is not None:
            return self.final
        return self.episodes[0].punishment if len(self.episodes) == 1 else None

    @property
    def imprisonment_months(self) -> int | None:
        """Final term of imprisonment, or the single count's term when there is no aggregate."""
        term = self.punishment
        if (
            term is not None
            and term.kind is PunishmentKind.IMPRISONMENT
            and term.unit is MeasureUnit.MONTHS
        ):
            return int(term.amount)
        return None
