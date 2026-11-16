"""Use case (T45.2, T45.3): a factual question asked in the chat, answered from facts by code.

Two kinds of question are answered without a case analysis: a practice question (T45.1,
src.application.practice_facts — numbers counted over the practice base) and a sanction
question (T45.3, src.application.sanction_facts — the punishments the statute in the law base
provides). A practice question is tried first: a question that asks for statistics is never a
sanction question. A language model, when one is connected, may only reword the answer written
by code: its text is shown only if every number in it is a number of those facts
(src.domain.answer_numbers); otherwise, or when the model is unavailable, the code's own answer
is shown. The sources are always added by code.
"""

from dataclasses import dataclass
from typing import Protocol

from src.application.practice_facts import PracticeFactStore, answer_practice_fact
from src.application.sanction_facts import SanctionReadings, answer_sanction_fact
from src.domain.answer_numbers import unsupported_numbers
from src.domain.practice_facts import PracticeTermFacts
from src.domain.practice_sources import describe_practice_sources

PRACTICE = "practice"
SANCTION = "sanction"


class AnswerPhraser(Protocol):
    async def phrase(self, qualification: str, facts_text: str) -> str | None:
        """The facts reworded for the user; None when the model gave no usable text."""
        ...


@dataclass(frozen=True)
class ChatPracticeAnswer:
    text: str
    facts: PracticeTermFacts | None  # None for a sanction question
    worded_by_model: bool
    # Numbers the model added and that made its wording unusable (empty when accepted).
    rejected_numbers: frozenset[str] = frozenset()
    kind: str = PRACTICE


async def _worded(
    phraser: AnswerPhraser | None, qualification: str, facts_text: str
) -> tuple[str, bool, frozenset[str]]:
    if phraser is None:
        return facts_text, False, frozenset()
    wording = await phraser.phrase(qualification, facts_text)
    if not wording or not wording.strip():
        return facts_text, False, frozenset()
    rejected = unsupported_numbers(wording, f"{qualification} {facts_text}")
    if rejected:
        return facts_text, False, rejected
    return wording.strip(), True, frozenset()


def _with_sources(body: str, sources: str) -> str:
    return f"{body}\n\n{sources}" if sources else body


async def answer_practice_question(
    store: PracticeFactStore | None,
    question: str,
    phraser: AnswerPhraser | None,
    sanctions: SanctionReadings | None = None,
) -> ChatPracticeAnswer | None:
    """None — not a factual question; the chat handles it as before.

    store None — the practice base is not used for this message; sanctions None — sanction
    questions are not answered here.
    """
    if store is not None:
        answer = await answer_practice_fact(store, question)
        if answer is not None:
            qualification = str(answer.facts.question.qualification)
            body, worded, rejected = await _worded(phraser, qualification, answer.text)
            sources = describe_practice_sources(answer.facts)
            return ChatPracticeAnswer(_with_sources(body, sources), answer.facts, worded, rejected)
    if sanctions is None:
        return None
    sanction = await answer_sanction_fact(sanctions, question)
    if sanction is None:
        return None
    qualification = str(sanction.facts.question.qualification)
    body, worded, rejected = await _worded(phraser, qualification, sanction.text)
    return ChatPracticeAnswer(
        _with_sources(body, sanction.source), None, worded, rejected, kind=SANCTION
    )
