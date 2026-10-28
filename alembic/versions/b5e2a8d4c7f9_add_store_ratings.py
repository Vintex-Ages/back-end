"""add store_ratings (#267)

Revision ID: b5e2a8d4c7f9
Revises: e8b4c2a7f1d3
Create Date: 2026-10-28

Avaliação da loja por estrelas, de 1 a 5 e sem comentário (RN-75), uma por
pedido entregue (RN-76). A nota fora da faixa é recusada pelo CHECK, e o
segundo voto no mesmo pedido pelo índice único.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b5e2a8d4c7f9"
down_revision: Union[str, None] = "e8b4c2a7f1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "store_ratings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_store_ratings_score"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_store_ratings_order_id", "store_ratings", ["order_id"], unique=True
    )
    op.create_index("ix_store_ratings_store_id", "store_ratings", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_store_ratings_store_id", table_name="store_ratings")
    op.drop_index("uq_store_ratings_order_id", table_name="store_ratings")
    op.drop_table("store_ratings")
