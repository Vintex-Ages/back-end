"""add user_preferences

Revision ID: 42fe2f7c474e
Revises: 998dd7b597f9
Create Date: 2026-09-09 20:07:31.088330

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "42fe2f7c474e"
down_revision: Union[str, None] = "998dd7b597f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "type",
            "value",
            name="uq_user_preferences_user_type_value",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
