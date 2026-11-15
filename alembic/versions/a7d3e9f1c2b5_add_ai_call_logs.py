"""add ai_call_logs

Revision ID: a7d3e9f1c2b5
Revises: c8f3b1e5d2a4
Create Date: 2026-11-14

Registro de cada chamada ao provedor de IA (back-end#263): qual funcionalidade
pediu, qual modelo respondeu, quanto demorou e se deu certo. Só medida, nenhum
texto da pergunta ou da peça.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7d3e9f1c2b5"
down_revision: Union[str, None] = "c8f3b1e5d2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copiadas do model de propósito: a migração descreve o banco como ele era
# nesta revisão, e não pode mudar se a lista do model mudar depois.
_FUNCIONALIDADES = (
    "'conversa', 'cadastro_foto', 'busca_imagem', 'recomendacao', "
    "'publicacao', 'backfill', 'nao_informada'"
)


def upgrade() -> None:
    op.create_table(
        "ai_call_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feature", sa.String(30), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            f"feature IN ({_FUNCIONALIDADES})", name="ck_ai_call_logs_feature"
        ),
        sa.CheckConstraint(
            "operation IN ('gerar', 'vetor')", name="ck_ai_call_logs_operation"
        ),
        sa.CheckConstraint("duration_ms >= 0", name="ck_ai_call_logs_duration"),
    )
    op.create_index("ix_ai_call_logs_created_at", "ai_call_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_created_at", table_name="ai_call_logs")
    op.drop_table("ai_call_logs")
