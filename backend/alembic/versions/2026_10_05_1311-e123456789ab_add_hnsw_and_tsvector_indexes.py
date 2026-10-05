"""add hnsw and tsvector indexes to document_chunks

Revision ID: e123456789ab
Revises: d94897fee201
Create Date: 2026-10-05 13:11:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e123456789ab"
down_revision: str | None = "d94897fee201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create HNSW index with cosine distance for semantic vector search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops);
        """
    )
    # Create GIN index on text tsvector for full-text keyword search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsvector
        ON document_chunks
        USING gin (to_tsvector('english', content));
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsvector;")
