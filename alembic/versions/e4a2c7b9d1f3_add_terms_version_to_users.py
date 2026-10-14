"""add terms_version e terms_accepted_at em users

Revision ID: e4a2c7b9d1f3
Revises: cfc160831d43
Create Date: 2026-10-14

Versão dos termos de uso aceita no cadastro (back-end#259, RN-93). As duas
colunas aceitam nulo: quem se cadastrou antes não tem versão gravada, e a
leitura desses usuários não pode quebrar.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e4a2c7b9d1f3"
down_revision: Union[str, None] = "cfc160831d43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("terms_version", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
