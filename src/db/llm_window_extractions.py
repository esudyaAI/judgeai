"""Cache of LLM readings of short text windows (idempotency and cost control).

Key: sha256 of the window, the field and the prompt version. The value is stored even when
the model found nothing, so the same window is never sent twice for the same prompt.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class LlmWindowExtraction(Base):
    __tablename__ = "llm_window_extractions"
    __table_args__ = (
        UniqueConstraint("input_hash", "field", "prompt_version", name="uq_llm_window_extraction"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrivateLlmWindowExtraction(Base):
    __tablename__ = "private_llm_window_extractions"
    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "input_hash",
            "field",
            "prompt_version",
            name="uq_private_llm_window_extraction",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict] = mapped_column(JSONB)
    provenance: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
