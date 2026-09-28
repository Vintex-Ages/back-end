"""add cart_items (#147)

Revision ID: d3f8a1b2c4e6
Revises: 7c2b1e4a8d91
Create Date: 2026-09-27 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f8a1b2c4e6"
down_revision: Union[str, None] = "7c2b1e4a8d91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cart_items",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_cart_items_user_product"),
    )
    op.create_index("ix_cart_items_user_id", "cart_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_cart_items_user_id", table_name="cart_items")
    op.drop_table("cart_items")
