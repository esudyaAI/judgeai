"""Use case (T45.7): the category of a crime (ст. 15 УК РФ) from the sanction in the law base.

The same readings as for a sanction question (T45.3) give the sanctions of the asked part from
the newest imported edition of the article, or refuse with ReferenceDataConflict;
src.domain.category_facts computes the category by the art. 15 rule of legal_core. No language
model takes part.
"""

from dataclasses import dataclass

from src.application.sanction_facts import SanctionReadings
from src.domain.category_facts import (
    CategoryFacts,
    describe_category_facts,
    describe_category_source,
    parse_category_question,
)
from src.domain.reference_conflict import ReferenceDataConflict


@dataclass(frozen=True)
class CategoryFactAnswer:
    facts: CategoryFacts
    text: str
    source: str  # written by code under the answer; empty when nothing was read


async def answer_category_fact(
    readings: SanctionReadings, question: str
) -> CategoryFactAnswer | None:
    parsed = parse_category_question(question)
    if parsed is None:
        return None
    target = parsed.target
    try:
        reading = await readings.article_sanctions(target.article, target.part)
    except ReferenceDataConflict:
        facts = CategoryFacts(parsed, (), None, conflict=True)
    else:
        sanctions, source = reading if reading is not None else ([], None)
        facts = CategoryFacts(parsed, tuple(sanctions), source)
    return CategoryFactAnswer(
        facts, describe_category_facts(facts), describe_category_source(facts)
    )
