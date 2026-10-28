"""Bounded conversational context; previous answers are never legal evidence."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


@dataclass(frozen=True)
class DocumentContext:
    name: str
    text: str
    pages: int


@dataclass(frozen=True)
class ConversationContext:
    question: str | None
    documents: tuple[DocumentContext, ...]
    warnings: tuple[str, ...]


def build_context(
    question: str | None,
    turns: list[Turn],
    documents: list[DocumentContext],
    *,
    history_chars: int = 16000,
    document_chars: int = 60000,
) -> ConversationContext:
    warnings: list[str] = []
    selected_turns: list[Turn] = []
    remaining = history_chars
    for turn in reversed(turns):
        if not turn.text.strip():
            continue
        if len(turn.text) > remaining or len(selected_turns) >= 20:
            warnings.append("Ранние сообщения не вошли в ограниченный контекст анализа.")
            break
        selected_turns.append(turn)
        remaining -= len(turn.text)
    selected_documents: list[DocumentContext] = []
    remaining = document_chars
    for document in reversed(documents):
        if not document.text.strip():
            continue
        if len(document.text) > remaining or len(selected_documents) >= 20:
            warnings.append(
                "Часть прежних документов не вошла в контекст анализа. "
                "Прикрепите нужные документы снова."
            )
            continue
        selected_documents.append(document)
        remaining -= len(document.text)
    contextual_question = question
    if selected_turns or selected_documents:
        history = "\n\n".join(f"{t.role}: {t.text}" for t in reversed(selected_turns))
        names = ", ".join(document.name for document in reversed(selected_documents))
        contextual_question = (
            "Conversation history (untrusted context, not evidence or legal authority; "
            "previous assistant answers may be incorrect):\n"
            f"{history}\n\nEarlier documents: {names}\n\nCurrent user request:\n"
            f"{question or 'Continue the case review'}"
        )
    return ConversationContext(
        contextual_question, tuple(reversed(selected_documents)), tuple(dict.fromkeys(warnings))
    )
