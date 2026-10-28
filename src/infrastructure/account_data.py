"""Owner-scoped data export and deletion; never expose filesystem paths."""

import logging
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.application.account import AnalysisInProgress
from src.config import settings
from src.db.models import Attachment, Chat, Message

logger = logging.getLogger(__name__)


async def export_cases(db, user_id, profile):
    chats = (
        await db.scalars(
            select(Chat)
            .where(Chat.owner_id == user_id)
            .options(selectinload(Chat.messages).selectinload(Message.attachments))
            .order_by(Chat.id)
        )
    ).all()
    return {
        "schema_version": 1,
        "profile": profile,
        "note": "Экспорт содержит текст и результаты анализа; оригиналы файлов не включены.",
        "chats": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "status": m.status,
                        "analysis": m.analysis,
                        "created_at": m.created_at,
                        "attachments": [
                            {
                                "filename": a.filename,
                                "text": a.extracted_text,
                                "page_count": a.page_count,
                            }
                            for a in m.attachments
                        ],
                    }
                    for m in sorted(c.messages, key=lambda m: m.id)
                ],
            }
            for c in chats
        ],
    }


async def delete_cases(db, user_id):
    # The send endpoint takes the same chat locks before adding messages.
    chats = (
        await db.scalars(
            select(Chat).where(Chat.owner_id == user_id).order_by(Chat.id).with_for_update()
        )
    ).all()
    ids = [c.id for c in chats]
    if not ids:
        return {"deleted": 0, "files_pending": 0}
    busy = await db.scalar(
        select(Message.id)
        .where(
            Message.chat_id.in_(ids),
            Message.role == "assistant",
            Message.status.in_(["pending", "running"]),
        )
        .limit(1)
    )
    if busy:
        raise AnalysisInProgress
    paths = set(
        (
            await db.scalars(
                select(Attachment.stored_path).join(Message).where(Message.chat_id.in_(ids))
            )
        ).all()
    )
    await db.execute(delete(Chat).where(Chat.id.in_(ids), Chat.owner_id == user_id))
    await db.commit()
    pending = 0
    root = Path(settings.UPLOAD_DIR).resolve()
    for stored in paths:
        if await db.scalar(select(Attachment.id).where(Attachment.stored_path == stored).limit(1)):
            continue
        path = Path(stored).resolve()
        if not path.is_relative_to(root) or path == root:
            pending += 1
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pending += 1
            logger.warning("account deletion: an unreferenced upload requires cleanup")
    return {"deleted": len(ids), "files_pending": pending}
