from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AnalysisRevision(Base):
    __tablename__ = "analysis_revisions"
    __table_args__ = (
        UniqueConstraint("source_message_id", "version", name="uq_analysis_revision_version"),
        UniqueConstraint("owner_id", "client_request_id", name="uq_analysis_revision_request"),
    )
    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    source_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    base_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analysis_revisions.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(20))
    calculation_inputs: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    inputs_sha256: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    result_sha256: Mapped[str] = mapped_column(String(64))
    review: Mapped[dict] = mapped_column(JSONB)
    client_request_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
