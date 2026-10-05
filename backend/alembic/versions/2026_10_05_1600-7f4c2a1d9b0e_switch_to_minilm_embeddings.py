"""switch document embeddings to MiniLM dimensions

Revision ID: 7f4c2a1d9b0e
Revises: 1a81ee739c47
Create Date: 2026-10-05 16:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f4c2a1d9b0e"
down_revision: str | None = "1a81ee739c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing vectors cannot be reused across embedding models or dimensions.
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DELETE FROM document_chunks")
    op.execute("UPDATE documents SET file_hash = NULL")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(384)")


def downgrade() -> None:
    op.execute("DELETE FROM document_chunks")
    op.execute("UPDATE documents SET file_hash = NULL")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024)")
