"""add embedding_status e embedding_error em products

Revision ID: c5e8a1f7b3d9
Revises: b7d3e91f4a26
Create Date: 2026-10-25

Situação e erro da geração do vetor da busca por semelhança na publicação
(back-end#245), como `ai_status`/`ai_error` registram a análise da foto. As duas
colunas aceitam nulo: o catálogo anterior a elas nunca teve geração pedida pela
publicação, e a leitura não pode quebrar.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c5e8a1f7b3d9"
down_revision: Union[str, None] = "b7d3e91f4a26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("embedding_status", sa.String(20), nullable=True)
    )
    op.add_column("products", sa.Column("embedding_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_products_embedding_status",
        "products",
        "embedding_status IS NULL"
        " OR embedding_status IN ('pending', 'done', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_products_embedding_status", "products", type_="check")
    op.drop_column("products", "embedding_error")
    op.drop_column("products", "embedding_status")
