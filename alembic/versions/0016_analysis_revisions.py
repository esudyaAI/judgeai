"""Immutable calculation inputs/results; no invented legacy inputs or reviewer backfill.

See docs/superpowers/plans/2026-11-04-fact-review.md for migration/rollback constraints.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_analysis_revisions"
down_revision = "0015_window_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "source_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "base_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_revisions.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("calculation_inputs", postgresql.JSONB(), nullable=True),
        sa.Column("inputs_sha256", sa.String(64), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("review", postgresql.JSONB(), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_message_id", "version", name="uq_analysis_revision_version"),
        sa.UniqueConstraint("owner_id", "client_request_id", name="uq_analysis_revision_request"),
    )
    op.create_index("ix_analysis_revisions_owner_id", "analysis_revisions", ["owner_id"])
    op.create_index("ix_analysis_revisions_chat_id", "analysis_revisions", ["chat_id"])


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Analysis revisions downgrade requires an online emptiness check")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM analysis_revisions)")):
        raise RuntimeError(
            "Analysis revisions contain records: archive explicitly before downgrade"
        )
    op.drop_table("analysis_revisions")
