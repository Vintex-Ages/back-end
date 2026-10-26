"""add composition em products

Revision ID: e8b4c2a7f1d3
Revises: d2f6b8c4a1e7
Create Date: 2026-10-26

Composição do tecido, lida da etiqueta pela análise da foto (back-end#257).
Aceita nulo: é opcional, a peça sem etiqueta legível fica sem ela, e as peças
gravadas antes desta coluna também.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e8b4c2a7f1d3"
down_revision: Union[str, None] = "d2f6b8c4a1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("composition", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "composition")
