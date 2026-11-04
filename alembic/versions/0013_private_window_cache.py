"""Keep private model readings inside their owning case.

No automatic backfill: ownership of old shared readings cannot be inferred safely.
Rollback keeps populated private records intact and requires an explicit archive first.
See docs/PRIVATE_WINDOW_CACHE_MIGRATION.md before any working-database migration.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_private_window_cache"
down_revision = "0012_chat_pins"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "private_llm_window_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("field", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "chat_id",
            "input_hash",
            "field",
            "prompt_version",
            name="uq_private_llm_window_extraction",
        ),
    )
    op.create_index(
        "ix_private_llm_window_extractions_chat_id", "private_llm_window_extractions", ["chat_id"]
    )


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Private cache downgrade requires an online emptiness check")
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM private_llm_window_extractions)"))
        .scalar()
    )
    if populated:
        raise RuntimeError("Private cache contains records: archive explicitly before downgrade")
    op.drop_table("private_llm_window_extractions")
