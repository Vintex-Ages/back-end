"""ensure one store per seller

Revision ID: 7c2b1e4a8d91
Revises: a1c2d3e4f5a6
Create Date: 2026-09-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "7c2b1e4a8d91"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("uq_stores_seller_id", "stores", ["seller_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_stores_seller_id", table_name="stores")
