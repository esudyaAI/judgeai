from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

# Message.status lifecycle for assistant messages:
#   pending -> running -> completed | failed
MESSAGE_STATUSES = ("pending", "running", "completed", "failed")
# Message.stage while running (drives the "analysis steps" UI):
ANALYSIS_STAGES = ("reading", "extracting", "checking", "searching", "recommending")
# Attachment.extraction_status:
#   ok | partial (some PDF pages had no text layer) | empty | unsupported | error
EXTRACTION_STATUSES = ("ok", "partial", "empty", "unsupported", "error")


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255))
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_chats_owner_id_users"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # onupdate fires only when the chat row itself changes; new messages touch it explicitly
    # (see api/chats.py) so the case list can be ordered by latest activity.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    request_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL", name="fk_messages_request_message_id"),
        index=True,
        unique=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str | None] = mapped_column(String(32))
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chat: Mapped["Chat"] = relationship(back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer, default=0)
    stored_path: Mapped[str] = mapped_column(String(1024))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extraction_status: Mapped[str] = mapped_column(String(16), default="ok", server_default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped["Message"] = relationship(back_populates="attachments")


class KnowledgeVerdict(Base):
    __tablename__ = "knowledge_verdicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str | None] = mapped_column(String(64), unique=True)
    case_number: Mapped[str | None] = mapped_column(String(64))
    court_name: Mapped[str | None] = mapped_column(Text)
    verdict_date: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_filename: Mapped[str | None] = mapped_column(String(512))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    structured: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="indexed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="verdict", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    verdict_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_verdicts.id", ondelete="CASCADE"), index=True
    )
    chunk_type: Mapped[str] = mapped_column(String(32), default="full_text")
    content: Mapped[str] = mapped_column(Text)
    # Any dimension: the vector belongs to embedding_model (migration 0011).
    embedding = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    verdict: Mapped["KnowledgeVerdict"] = relationship(back_populates="chunks")


# Register the public legal corpus and derived sanctions in the metadata used by Alembic.
from src.db.auth import LoginBucket, User, UserSession  # noqa: E402,F401
from src.db.criminal_sanctions import CriminalArticleSanction  # noqa: E402,F401
from src.db.legal_library import LegalAct, LegalEdition, LegalProvision, LegalRuleReference  # noqa: E402,F401
from src.db.llm_window_extractions import LlmWindowExtraction  # noqa: E402,F401
from src.db.precedents import PrecedentCardField, PrecedentCardRow, PrecedentEmbedding  # noqa: E402,F401
