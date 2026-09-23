"""add rascunho status and product ai corrections

Revision ID: a10906201913
Revises: a1c2d3e4f5a6
Create Date: 2026-09-21 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a10906201913"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_products_status", "products", type_="check")
    op.create_check_constraint(
        "ck_products_status",
        "products",
        "status IN ('rascunho', 'ativo', 'vendido', 'despublicado')",
    )

    op.create_table(
        "product_ai_corrections",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("suggested", sa.Text(), nullable=True),
        sa.Column("final", sa.Text(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_ai_corrections_product_id"),
        "product_ai_corrections",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_product_ai_corrections_product_id"),
        table_name="product_ai_corrections",
    )
    op.drop_table("product_ai_corrections")

    op.drop_constraint("ck_products_status", "products", type_="check")
    op.create_check_constraint(
        "ck_products_status",
        "products",
        "status IN ('ativo', 'vendido', 'despublicado')",
    )
