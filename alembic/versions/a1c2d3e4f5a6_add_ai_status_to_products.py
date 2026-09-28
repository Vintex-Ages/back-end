"""add ai_status, ai_suggestions and ai_error to products

Revision ID: a1c2d3e4f5a6
Revises: 0f9a7f647244
Create Date: 2026-09-18 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f5a6"
down_revision: Union[str, None] = "0f9a7f647244"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("ai_status", sa.String(length=20), nullable=True)
    )
    op.add_column("products", sa.Column("ai_suggestions", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("ai_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_products_ai_status",
        "products",
        "ai_status IS NULL OR ai_status IN ('pending', 'processing', 'done', 'failed')",
    )
    op.create_index("ix_products_ai_status", "products", ["ai_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_ai_status", table_name="products")
    op.drop_constraint("ck_products_ai_status", "products", type_="check")
    op.drop_column("products", "ai_error")
    op.drop_column("products", "ai_suggestions")
    op.drop_column("products", "ai_status")
