"""Owner-scoped chat search without exposing message text in search responses."""

from sqlalchemy import or_, select

from src.db.models import Attachment, Chat, Message


def owned_chat_query(user_id: int, query: str):
    statement = select(Chat).where(Chat.owner_id == user_id)
    if query := query.strip():
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        matches_message = (
            select(Message.id)
            .where(Message.chat_id == Chat.id, Message.content.ilike(pattern, escape="\\"))
            .exists()
        )
        matches_file = (
            select(Attachment.id)
            .join(Message)
            .where(Message.chat_id == Chat.id, Attachment.filename.ilike(pattern, escape="\\"))
            .exists()
        )
        statement = statement.where(
            or_(Chat.title.ilike(pattern, escape="\\"), matches_message, matches_file)
        )
    return statement.order_by(Chat.updated_at.desc(), Chat.id.desc())
