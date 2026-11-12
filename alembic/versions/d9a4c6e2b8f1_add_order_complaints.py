"""add order_complaints (#268)

Revision ID: d9a4c6e2b8f1
Revises: c8f3b1e5d2a4
Create Date: 2026-11-12

Reclamação do comprador sobre um pedido, por não recebimento ou dano (RN-77).
O motivo fora dos dois valores é recusado pelo CHECK, e a segunda reclamação
no mesmo pedido pelo índice único.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d9a4c6e2b8f1"
down_revision: Union[str, None] = "c8f3b1e5d2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_complaints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "reason IN ('nao_recebido', 'danificado')",
            name="ck_order_complaints_reason",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_order_complaints_order_id", "order_complaints", ["order_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_order_complaints_order_id", table_name="order_complaints")
    op.drop_table("order_complaints")
