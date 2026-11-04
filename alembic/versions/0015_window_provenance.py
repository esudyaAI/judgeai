"""Preserve original provider metadata beside cached window readings, without legacy backfill."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0015_window_provenance"
down_revision = "0014_case_reports"
branch_labels = None
depends_on = None

TABLES = ("llm_window_extractions", "private_llm_window_extractions")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("provenance", postgresql.JSONB(), nullable=True))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Cannot verify provenance archive in offline downgrade")
    for table in TABLES:
        if op.get_bind().scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} "
                "WHERE provenance IS NOT NULL AND provenance <> 'null'::jsonb)"
            )
        ):
            raise RuntimeError(
                "Window provenance contains records: archive explicitly before downgrade"
            )
    for table in reversed(TABLES):
        op.drop_column(table, "provenance")
