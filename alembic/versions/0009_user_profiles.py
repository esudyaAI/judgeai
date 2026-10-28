"""Private account profiles; existing accounts lazily receive empty defaults.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_user_profiles"
down_revision = "0008_precedent_embeddings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("user_profiles")
