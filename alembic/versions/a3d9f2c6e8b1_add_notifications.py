"""add notifications (#261)

Revision ID: a3d9f2c6e8b1
Revises: e8b4c2a7f1d3
Create Date: 2026-10-28

Aviso in-app ao usuário (RN-84), com os dois eventos da RN-85: a venda, ao
vendedor, quando a administradora aprova o comprovante, e o favorito, ao
anunciante. O índice único parcial impede o mesmo favorito de avisar duas
vezes depois de desfavoritar e favoritar de novo.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a3d9f2c6e8b1"
down_revision: Union[str, None] = "e8b4c2a7f1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "type IN ('sale', 'favorite')", name="ck_notifications_type"
        ),
        sa.CheckConstraint(
            "(type = 'sale' AND order_id IS NOT NULL)"
            " OR (type <> 'sale' AND order_id IS NULL)",
            name="ck_notifications_order",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "uq_notifications_favorite",
        "notifications",
        ["product_id", "actor_id"],
        unique=True,
        postgresql_where=sa.text("type = 'favorite'"),
    )


def downgrade() -> None:
    op.drop_index("uq_notifications_favorite", table_name="notifications")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
