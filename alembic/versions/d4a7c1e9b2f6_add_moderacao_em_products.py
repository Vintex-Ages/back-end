"""moderação de anúncios: motivo, data e autor na peça (#327)

Revision ID: d4a7c1e9b2f6
Revises: c8f3b1e5d2a4
Create Date: 2026-11-04

A peça que a administradora tira do ar (RN-80) precisa se distinguir da peça
que o próprio vendedor pausou: as duas são `despublicado` no status. As três
colunas guardam quem moderou, quando e por quê, e são o que o `publish` do
vendedor consulta para recusar a republicação.

Sem tabela nova e sem alterar o `CheckConstraint` do status: `despublicado` já
existe. O aviso ao vendedor usa a tabela de notificações (#261), que ganha o
terceiro tipo — o modelo já dizia que ele entraria aqui.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4a7c1e9b2f6"
down_revision: Union[str, None] = "c8f3b1e5d2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("moderation_reason", sa.String(500), nullable=True)
    )
    op.add_column("products", sa.Column("moderated_at", sa.DateTime(), nullable=True))
    op.add_column(
        "products", sa.Column("moderated_by_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_products_moderated_by_id_users",
        "products",
        "users",
        ["moderated_by_id"],
        ["id"],
    )

    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ('sale', 'favorite', 'moderation')",
    )


def downgrade() -> None:
    # O CHECK antigo não aceita o tipo novo: as linhas precisam sair antes de
    # ele voltar, senão o downgrade falha com dado de moderação gravado.
    op.execute("DELETE FROM notifications WHERE type = 'moderation'")
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ('sale', 'favorite')",
    )

    op.drop_constraint(
        "fk_products_moderated_by_id_users", "products", type_="foreignkey"
    )
    op.drop_column("products", "moderated_by_id")
    op.drop_column("products", "moderated_at")
    op.drop_column("products", "moderation_reason")
