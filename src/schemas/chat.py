from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Derived from the latest assistant message: no analysis yet -> draft,
# pending/running -> busy, completed -> ready, failed -> failed.
ChatStatus = Literal["draft", "busy", "ready", "failed"]


class ChatCreate(BaseModel):
    title: str | None = None


class ChatPin(BaseModel):
    pinned: bool


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    status: ChatStatus = "draft"
    is_pinned: bool = False
