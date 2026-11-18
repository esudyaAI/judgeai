"""Use case (T45.3): answer «what does the law provide» from the sanctions in the law base.

The readings give the sanctions of the asked part from the newest imported edition of the
article (or refuse with ReferenceDataConflict); src.domain.sanction_facts turns them into the
answer. No language model takes part: a question the domain does not recognise is not
answered here.
"""

from dataclasses import dataclass
from typing import Protocol

from legal_core.entities import StatutorySanction

from src.domain.reference_conflict import ReferenceDataConflict
from src.domain.sanction_facts import (
    SanctionFacts,
    SanctionSource,
    describe_date_note,
    describe_sanction_facts,
    describe_sanction_source,
    parse_sanction_question,
)


class SanctionReadings(Protocol):
    async def article_sanctions(
        self, article: str, part: int | None
    ) -> tuple[list[StatutorySanction], SanctionSource] | None:
        """None — the part is not parsed; ReferenceDataConflict — editions contradict."""
        ...


@dataclass(frozen=True)
class SanctionFactAnswer:
    facts: SanctionFacts
    text: str
    source: str  # written by code under the answer; empty when nothing was read
    date_note: str = ""  # T45.9: written by code after the answer; empty without a date


async def answer_sanction_fact(
    readings: SanctionReadings, question: str
) -> SanctionFactAnswer | None:
    parsed = parse_sanction_question(question)
    if parsed is None:
        return None
    target = parsed.target
    try:
        reading = await readings.article_sanctions(target.article, target.part)
    except ReferenceDataConflict:
        facts = SanctionFacts(parsed, (), None, conflict=True)
    else:
        sanctions, source = reading if reading is not None else ([], None)
        facts = SanctionFacts(parsed, tuple(sanctions), source)
    return SanctionFactAnswer(
        facts,
        describe_sanction_facts(facts),
        describe_sanction_source(facts),
        describe_date_note(facts),
    )
