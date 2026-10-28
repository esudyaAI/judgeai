"""Single-chat deletion through an owner-scoped persistence port."""

from typing import Protocol


class ChatNotFound(Exception):
    pass


class ChatDeletionRepository(Protocol):
    async def delete_chat(self, user_id: int, chat_id: int) -> dict: ...


async def delete_chat(repository: ChatDeletionRepository, user_id: int, chat_id: int) -> dict:
    result = await repository.delete_chat(user_id, chat_id)
    if not result["deleted"]:
        raise ChatNotFound
    return result
