"""add ai_chat_usage

Revision ID: d2f6b8c4a1e7
Revises: c5e8a1f7b3d9
Create Date: 2026-10-26

Contagem diária de perguntas ao chat, por pessoa e para o projeto, que sustenta
a cota da busca conversacional (back-end#258). Uma linha por (dia, chave).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d2f6b8c4a1e7"
down_revision: Union[str, None] = "c5e8a1f7b3d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("day", "key", name="uq_ai_chat_usage_day_key"),
        sa.CheckConstraint("count >= 0", name="ck_ai_chat_usage_count"),
    )


def downgrade() -> None:
    op.drop_table("ai_chat_usage")
