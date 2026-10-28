"""Attachment lookup never trusts a stored path outside private upload storage."""

from pathlib import Path

from sqlalchemy import select

from src.application.document_preview import AttachmentSource, PreviewNotFound
from src.db.models import Attachment, Chat, Message


class SqlAttachmentRepository:
    def __init__(self, db, upload_dir: Path):
        self.db = db
        self.upload_dir = upload_dir.resolve()

    async def get(self, owner: int, chat: int, attachment: int) -> AttachmentSource:
        record = await self.db.scalar(
            select(Attachment)
            .join(Message, Message.id == Attachment.message_id)
            .join(Chat, Chat.id == Message.chat_id)
            .where(Attachment.id == attachment, Chat.id == chat, Chat.owner_id == owner)
        )
        if record is None:
            raise PreviewNotFound
        path = Path(record.stored_path)
        resolved = path.resolve()
        if (
            path.is_symlink()
            or not resolved.is_relative_to(self.upload_dir)
            or not resolved.is_file()
        ):
            raise PreviewNotFound
        return AttachmentSource(str(resolved), resolved.suffix, record.filename)
