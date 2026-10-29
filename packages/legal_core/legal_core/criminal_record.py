"""Criminal record facts -> art.18 inputs, with explicit "unknown" handling.

Turns dated facts of prior judgments into the boolean conditions of art.18 part 4
(see ``legal_core.rules.art18``). A missing or ambiguous fact that could change the
result yields ``None`` ("cannot decide"), never a silent "no recidivism".

Sources checked 2026-10-28 (needs_legal_review=True, sign-off pending in T3):
- Criminal Code art.18 part 4, art.86 part 1 (record arises when the judgment
  enters into force), edition 2026-08-04;
- Plenum of the Supreme Court No.1 of 2011-02-01, para.7: a person reaches an age
  from 00:00 of the day following the birthday;
- Civil Code art.192 part 3: a term ending in a month without that day ends on the
  last day of the month (applied to a 29 February birthday).
Whether the record still existed on the day of the new offence (art.86) is computed by
``legal_core.rules.art86.record_active_on`` when the caller passes the sentence facts
(``Conviction.expungement``, T3.1); otherwise the caller-supplied ``active_at_offence`` is
used. When both are given and disagree, the result is "cannot decide" (no silent choice).
"""

import calendar
from dataclasses import dataclass
from datetime import date

from legal_core.entities import Category, Guilt
from legal_core.rules.art18 import CurrentOffence, PriorConviction, Recidivism, classify_recidivism
from legal_core.rules.art86 import Disposition, SentenceForExpungement, record_active_on

NEEDS_LEGAL_REVIEW = True
ADULT_AGE = 18


def eighteenth_birthday(birth: date) -> date:
    year = birth.year + ADULT_AGE
    day = min(birth.day, calendar.monthrange(year, birth.month)[1])
    return date(year, birth.month, day)


def adult_on(birth: date, day: date) -> bool:
    return day > eighteenth_birthday(birth)


@dataclass(frozen=True)
class Conviction:
    """One prior judgment (not one count). ``None`` means the fact is unknown."""

    judgment_id: str
    guilt: Guilt
    category: Category
    offence_date: date | None
    legal_force_date: date | None
    imprisoned_by_sentence: bool
    conditional_or_deferred: bool
    # Legacy physical transfer date; retained for callers, never proves the court decision.
    sent_to_prison_on: date | None
    active_at_offence: bool | None
    # Date of the court decision revoking suspension and directing imprisonment.
    # None means unknown; physical transfer/start of custody is not decisive (Plenum 58 p.45).
    revocation_decision_date: date | None = None
    # Facts for ч. 3 ст. 86 / ст. 95; when given, the record on the offence day is computed.
    expungement: SentenceForExpungement | None = None

    def __post_init__(self) -> None:
        s = self.expungement
        if s is None:
            return
        if s.category is not self.category:
            raise ValueError("expungement.category differs from the conviction category")
        for name in ("legal_force_date", "offence_date"):
            mine, theirs = getattr(self, name), getattr(s, name)
            if mine is not None and theirs is not None and mine != theirs:
                raise ValueError(f"expungement.{name} differs from the conviction")
        if s.disposition is Disposition.CONDITIONAL and not self.conditional_or_deferred:
            raise ValueError("a conditional disposition needs conditional_or_deferred=True")


@dataclass(frozen=True)
class CriminalRecord:
    birth_date: date | None
    convictions: tuple[Conviction, ...]
    # False when the history (e.g. ИЦ МВД certificate) was not fully established.
    complete: bool

    def priors_for(self, offence_date: date) -> list[PriorConviction] | None:
        """Art.18 inputs for a new offence, or None if any decisive fact is unknown."""
        priors = [self._prior(c, offence_date) for c in self.convictions]
        if any(p is None for p in priors):
            return None
        return [p for p in priors if p is not None]

    def _prior(self, c: Conviction, offence_date: date) -> PriorConviction | None:
        adult = (
            None
            if self.birth_date is None or c.offence_date is None
            else adult_on(self.birth_date, c.offence_date)
        )
        active = active_at(c, offence_date)
        before = _strictly_before(c.legal_force_date, offence_date)
        if not c.conditional_or_deferred:
            revoked = False
        else:
            revoked = _strictly_before(c.revocation_decision_date, offence_date)
        conditions = [
            c.guilt == Guilt.INTENTIONAL,
            c.category != Category.SMALL,
            adult,
            active,
            before,
            True if not c.conditional_or_deferred else revoked,
        ]
        if False not in conditions and None in conditions:
            return None
        return PriorConviction(
            judgment_id=c.judgment_id,
            guilt=c.guilt,
            category=c.category,
            adult_at_offence=bool(adult),
            active_at_offence=bool(active),
            convicted_before_offence=bool(before),
            imprisoned_by_sentence=c.imprisoned_by_sentence,
            conditional_or_deferred=c.conditional_or_deferred,
            revoked_and_sent_before_offence=bool(revoked),
        )


def active_at(c: Conviction, offence_date: date) -> bool | None:
    """Whether the record of ``c`` existed on ``offence_date``; None — cannot decide.

    The caller's value (e.g. from an ИЦ МВД certificate) fills a day the art.86 rule leaves
    open; a disagreement between the two is never resolved silently.
    """
    if c.expungement is None:
        return c.active_at_offence
    computed = record_active_on(c.expungement, offence_date)
    if computed is None:
        return c.active_at_offence
    if c.active_at_offence is None or c.active_at_offence == computed:
        return computed
    return None


def _strictly_before(event: date | None, offence_date: date) -> bool | None:
    # Same day: the order of events within the day is not known from dates alone.
    if event is None or event == offence_date:
        return None
    return event < offence_date


def classify_record(
    record: CriminalRecord, current: CurrentOffence, offence_date: date
) -> Recidivism:
    if current.guilt == Guilt.NEGLIGENT:
        return Recidivism.NONE
    priors = record.priors_for(offence_date)
    if priors is None:
        return Recidivism.UNKNOWN
    return classify_recidivism(current, priors, history_complete=record.complete)
