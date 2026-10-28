"""add receipt_name e receipt_content_type em payments

Revision ID: b7d3e91f4a26
Revises: e4a2c7b9d1f3
Create Date: 2026-10-25

Nome original e tipo do comprovante, gravados no envio (back-end#244). A chave
do storage é um uuid sem extensão, então o nome não tem de onde sair, e o tipo
só sairia baixando o arquivo. As duas colunas aceitam nulo: linha gravada antes
delas não tem os dois dados, e a leitura não pode quebrar.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7d3e91f4a26"
down_revision: Union[str, None] = "e4a2c7b9d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("receipt_name", sa.String(255), nullable=True))
    op.add_column(
        "payments", sa.Column("receipt_content_type", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("payments", "receipt_content_type")
    op.drop_column("payments", "receipt_name")
