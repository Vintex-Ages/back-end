"""add embedding vector and embedding_model to products (BE-US027-1, #92)

Revision ID: b7e1f2a3c4d5
Revises: a1c2d3e4f5a6
Create Date: 2026-09-25 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e1f2a3c4d5"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "products", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True)
    )
    op.add_column(
        "products", sa.Column("embedding_model", sa.String(length=60), nullable=True)
    )
    # ivfflat com `lists=1`: adequado ao catálogo de seed (60 peças). Revisar
    # `lists` (regra de bolso: sqrt(linhas)) quando o catálogo crescer de
    # verdade — hoje otimizar isso seria prematuro.
    op.execute(
        "CREATE INDEX ix_products_embedding ON products "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 1)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_embedding")
    op.drop_column("products", "embedding_model")
    op.drop_column("products", "embedding")
