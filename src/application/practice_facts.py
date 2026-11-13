"""Use case (T45.1): answer a factual practice question with numbers counted by code.

The store gives every practice card that has the asked article in any count; which of them
are comparable and what they add up to is decided by src.domain.practice_facts. No language
model takes part: a question the domain does not recognise is not answered here.
"""

from dataclasses import dataclass
from typing import Protocol

from src.application.similar_precedents import StoredCard
from src.domain.practice_facts import (
    PracticeTermFacts,
    PracticeVerdict,
    describe_practice_term_facts,
    parse_practice_term_question,
    practice_term_facts,
)


class PracticeFactStore(Protocol):
    async def cards_with_article(self, article: str) -> list[StoredCard]: ...


@dataclass(frozen=True)
class PracticeFactAnswer:
    facts: PracticeTermFacts
    text: str


async def answer_practice_fact(
    store: PracticeFactStore, question: str
) -> PracticeFactAnswer | None:
    parsed = parse_practice_term_question(question)
    if parsed is None:
        return None
    stored = await store.cards_with_article(parsed.qualification.article)
    verdicts = [
        PracticeVerdict(s.id, s.card, s.court_name, s.decision_date, s.source_url, s.uid)
        for s in stored
    ]
    facts = practice_term_facts(parsed, verdicts)
    return PracticeFactAnswer(facts, describe_practice_term_facts(facts))
