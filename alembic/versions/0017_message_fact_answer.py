"""T45.4: marker of an answer read by code (practice or sanction facts) on a message.

`messages.fact_answer` is a nullable JSONB written only for an answer the chat built from facts
read by code ({"kind": "practice" | "sanction", "worded_by_model": bool}); the interface marks
such an answer and opens its sources as links. No backfill: earlier answers keep their text and
show no marker. Downgrade drops only this display marker — the answer text in
`messages.content` (with its sources) stays, so nothing the user read is lost.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_message_fact_answer"
down_revision = "0016_analysis_revisions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("fact_answer", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("messages", "fact_answer")
