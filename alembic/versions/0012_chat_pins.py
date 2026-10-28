"""Persist owner chat pins without changing messages or chat activity.

Backfill: the constant false default preserves existing order until a user pins a chat.
Rollback: drop only is_pinned; chat contents, owners and files remain intact.
Production uses the existing pre-migration backup gate.
"""

import sqlalchemy as sa
from alembic import op

revision = '0012_chat_pins'
down_revision = '0011_embedding_any_dimension'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chats', sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('chats', 'is_pinned')
