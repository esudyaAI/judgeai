from sqlalchemy import update

from src.db.models import Chat


class SqlChatPinRepository:
    def __init__(self, db):
        self.db = db

    async def set_pinned(self, owner: int, chat_id: int, pinned: bool) -> bool:
        result = await self.db.scalar(
            update(Chat)
            .where(Chat.id == chat_id, Chat.owner_id == owner)
            .values(is_pinned=pinned, updated_at=Chat.updated_at)
            .returning(Chat.id)
        )
        await self.db.commit()
        return result is not None
