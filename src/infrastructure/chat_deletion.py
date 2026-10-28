"""Reuse the same locking, cascade and safe file cleanup as account deletion."""

from src.infrastructure.account_data import delete_cases


class SqlChatDeletionRepository:
    def __init__(self, db):
        self.db = db

    async def delete_chat(self, user_id: int, chat_id: int) -> dict:
        return await delete_cases(self.db, user_id, chat_id=chat_id)
