"""Immutable private report snapshots and generated DOCX; no automatic legacy backfill.

See docs/superpowers/plans/2026-11-04-case-reports.md before a working-database migration.
A populated table is preserved on downgrade until an explicit archive is approved.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_case_reports"
down_revision = "0013_private_window_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_reports",
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
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("docx_data", sa.LargeBinary(), nullable=False),
        sa.Column("docx_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("chat_id", "version", name="uq_case_report_version"),
        sa.UniqueConstraint("chat_id", "snapshot_sha256", name="uq_case_report_snapshot"),
    )
    op.create_index("ix_case_reports_owner_id", "case_reports", ["owner_id"])
    op.create_index("ix_case_reports_chat_id", "case_reports", ["chat_id"])


def downgrade():
    if op.get_context().as_sql:
        raise RuntimeError("Report downgrade requires an online emptiness check")
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM case_reports)")).scalar():
        raise RuntimeError("Reports contain records: archive explicitly before downgrade")
    op.drop_table("case_reports")
