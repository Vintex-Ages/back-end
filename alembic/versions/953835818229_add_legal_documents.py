"""add legal_documents (termos de uso e contrato de venda versionados)

Revision ID: 953835818229
Revises: a1c2d3e4f5a6
Create Date: 2026-09-25 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "953835818229"
down_revision: Union[str, None] = "a1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_documents",
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "document_type IN ('termos_uso', 'contrato_venda')",
            name="ck_legal_documents_document_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_type", "version", name="uq_legal_documents_type_version"
        ),
    )


def downgrade() -> None:
    op.drop_table("legal_documents")
