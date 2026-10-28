"""Owner-scoped pinning without changing a chat's conversation activity."""

from typing import Protocol

from src.application.chat_deletion import ChatNotFound


class ChatPinRepository(Protocol):
    async def set_pinned(self, owner: int, chat_id: int, pinned: bool) -> bool: ...


async def pin_chat(repository: ChatPinRepository, owner: int, chat_id: int, pinned: bool) -> None:
    if not await repository.set_pinned(owner, chat_id, pinned):
        raise ChatNotFound
