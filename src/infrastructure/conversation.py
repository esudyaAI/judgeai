"""Read earlier completed turns and extracted documents from one owned chat."""

import json

from sqlalchemy import func, select

from src.db.models import Attachment, Chat, Message
from src.domain.conversation import DocumentContext, Turn, build_context


def _answer(message: Message) -> str:
    if message.role != "assistant" or not message.analysis:
        return message.content or ""
    # Include the answer the user actually saw, not only its fabula column.
    keys = ("fabula", "qualification", "variants", "scale", "legal_checks", "warnings")
    result = {key: message.analysis[key] for key in keys if key in message.analysis}
    return json.dumps(result, ensure_ascii=False)


async def load_conversation(db, user_id: int, chat_id: int, request_id: int, question: str | None):
    scope = (
        Chat.owner_id == user_id,
        Message.chat_id == chat_id,
        Message.id < request_id,
        Message.status == "completed",
    )
    messages = list(
        await db.scalars(
            select(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(*scope)
            .order_by(Message.id.desc())
            .limit(40)
        )
    )
    messages.reverse()
    turns = [Turn(message.role, _answer(message)) for message in messages]
    # Documents have an independent budget: a first-turn upload stays available
    # even after the conversational turn window has moved on. Bound SQL payload too.
    records = list(
        (
            await db.execute(
                select(
                    Attachment.filename,
                    func.left(Attachment.extracted_text, 60001),
                    Attachment.page_count,
                )
                .join(Message, Message.id == Attachment.message_id)
                .join(Chat, Chat.id == Message.chat_id)
                .where(
                    *scope,
                    Message.role == "user",
                    Attachment.extraction_status.in_(("ok", "partial")),
                    Attachment.extracted_text.is_not(None),
                )
                .order_by(Attachment.id.desc())
                .limit(21)
            )
        ).all()
    )
    documents = [
        DocumentContext(name, text or "", pages or 0) for name, text, pages in reversed(records)
    ]
    return build_context(question, turns, documents)
