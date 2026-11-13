"""Use case (T45.2): a practice question asked in the chat, answered from facts counted by code.

The numbers come from T45.1 (src.application.practice_facts). A language model, when one is
connected, may only reword the answer written by code: its text is shown only if every number
in it is a number of those facts (src.domain.answer_numbers); otherwise, or when the model is
unavailable, the code's own answer is shown. The list of sources is always added by code.
"""

from dataclasses import dataclass
from typing import Protocol

from src.application.practice_facts import PracticeFactStore, answer_practice_fact
from src.domain.answer_numbers import unsupported_numbers
from src.domain.practice_facts import PracticeTermFacts
from src.domain.practice_sources import describe_practice_sources


class AnswerPhraser(Protocol):
    async def phrase(self, qualification: str, facts_text: str) -> str | None:
        """The facts reworded for the user; None when the model gave no usable text."""
        ...


@dataclass(frozen=True)
class ChatPracticeAnswer:
    text: str
    facts: PracticeTermFacts
    worded_by_model: bool
    # Numbers the model added and that made its wording unusable (empty when accepted).
    rejected_numbers: frozenset[str] = frozenset()


async def answer_practice_question(
    store: PracticeFactStore, question: str, phraser: AnswerPhraser | None
) -> ChatPracticeAnswer | None:
    """None — not a factual practice question; the chat handles it as before."""
    answer = await answer_practice_fact(store, question)
    if answer is None:
        return None
    qualification = str(answer.facts.question.qualification)
    body, worded, rejected = answer.text, False, frozenset()
    if phraser is not None:
        wording = await phraser.phrase(qualification, answer.text)
        if wording and wording.strip():
            rejected = unsupported_numbers(wording, f"{qualification} {answer.text}")
            if not rejected:
                body, worded = wording.strip(), True
    sources = describe_practice_sources(answer.facts)
    text = f"{body}\n\n{sources}" if sources else body
    return ChatPracticeAnswer(text, answer.facts, worded, rejected)
