"""Vectors of any dimension, tagged with the model that produced them (Jina cloud, T8).

knowledge_chunks.embedding and precedent_embeddings.embedding lose their fixed dimension, so
switching EMBEDDING_MODEL (e.g. to the 1024-dimensional jina-embeddings-v3) needs no schema
change; search compares only vectors of the configured model. These columns have no vector
indexes, so nothing is rebuilt.

Backfill: knowledge_chunks.embedding_model is set to EMBEDDING_MODEL for vectors of the
configured EMBEDDING_DIM; vectors of another dimension get "unknown-<dim>" and are re-embedded
by `python -m src.cli.precedents index`. precedent_embeddings already carries its model.

Downgrade: vectors whose dimension differs from EMBEDDING_DIM are dropped (chunks keep their
text; precedent vectors are recomputed by the same command), the model column is removed and
the columns return to vector(EMBEDDING_DIM), as created by 0001 and 0008.
"""

import sqlalchemy as sa
from alembic import op

from src.config import settings

revision = "0011_embedding_any_dimension"
down_revision = "0010_merge_profiles_defendants"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector")
    op.execute("ALTER TABLE precedent_embeddings ALTER COLUMN embedding TYPE vector")
    op.add_column("knowledge_chunks", sa.Column("embedding_model", sa.String(255), nullable=True))
    op.execute(
        sa.text(
            "UPDATE knowledge_chunks SET embedding_model = CASE "
            "WHEN vector_dims(embedding) = :dim THEN :model "
            "ELSE 'unknown-' || vector_dims(embedding) END "
            "WHERE embedding IS NOT NULL"
        ).bindparams(dim=settings.EMBEDDING_DIM, model=settings.EMBEDDING_MODEL)
    )


def downgrade():
    dim = int(settings.EMBEDDING_DIM)
    op.execute(f"DELETE FROM precedent_embeddings WHERE vector_dims(embedding) <> {dim}")
    op.execute(f"UPDATE knowledge_chunks SET embedding = NULL WHERE vector_dims(embedding) <> {dim}")
    op.drop_column("knowledge_chunks", "embedding_model")
    op.execute(f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({dim})")
    op.execute(f"ALTER TABLE precedent_embeddings ALTER COLUMN embedding TYPE vector({dim})")
