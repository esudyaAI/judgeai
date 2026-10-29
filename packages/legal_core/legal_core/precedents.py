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


# The same spans feed both card qualification and punishment attribution.
_QUALIFICATION = re.compile(
    r'(?:п(?:\.\s*п)?\.\s*[«"“]?(?P<points>[а-яё](?:\s*,\s*[а-яё])*)[»"”)]?\s*)?'
    r"(?:ч\.\s*(?P<part>\d{1,2})\s*)?ст\.\s*(?P<article>\d{1,3}(?:\.\d{1,2})?)(?!\d)"
    r"(?:\s*ч\.\s*(?P<part_after>\d{1,2}))?",
    re.IGNORECASE,
)
_CITATION_CODE = re.compile(
    r"^\s*(?:(?:,|и|[-–—])\s*(?:ч\.\s*\d{1,2}\s*)?(?:ст\.\s*)?\d{1,3}(?:\.\d{1,2})?\s*)*\s*(?P<code>УПК|КоАП|ГПК|АПК|ГК|НК|СК|ТК|УК)\b",
    re.I,
)


@dataclass(frozen=True)
class QualificationCitation:
    start: int
    end: int
    qualifications: tuple[Qualification, ...]


def qualification_citations(text: str) -> tuple[QualificationCitation, ...]:
    """Criminal references with their exact spans; another code affects only its own citation."""
    found = []
    for match in _QUALIFICATION.finditer(text):
        if int(match["article"].split(".")[0]) < FIRST_SPECIAL_PART_ARTICLE:
            continue
        code = _CITATION_CODE.match(text[match.end() :])
        if code and code["code"].upper() != "УК":
            continue
        part_text = match["part"] or match["part_after"]
        if match["part"] and match["part_after"] and match["part"] != match["part_after"]:
            continue
        part = int(part_text) if part_text else None
        if part is not None and part <= 0:
            continue
        points = re.findall(r"[а-яё]", (match["points"] or "").lower()) or [None]
        qualifications = tuple(Qualification(match["article"], part, point) for point in points)
        found.append(QualificationCitation(match.start(), match.end(), qualifications))
    return tuple(found)


def parse_qualifications(text: str) -> tuple[Qualification, ...]:
    """All distinct Special Part qualifications in source order, including multiple points."""
    return tuple(
        dict.fromkeys(
            q for citation in qualification_citations(text) for q in citation.qualifications
        )
    )


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
    def imprisonment_months(self) -> int | None:
        """Final term of imprisonment, or the single count's term when there is no aggregate."""
        term = self.final
        if term is None and len(self.episodes) == 1:
            term = self.episodes[0].punishment
        if (
            term is not None
            and term.kind is PunishmentKind.IMPRISONMENT
            and term.unit is MeasureUnit.MONTHS
        ):
            return int(term.amount)
        return None
