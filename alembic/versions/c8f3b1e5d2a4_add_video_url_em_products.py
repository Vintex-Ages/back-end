"""add video_url em products (#270)

Revision ID: c8f3b1e5d2a4
Revises: b5e2a8d4c7f9
Create Date: 2026-10-28

Vínculo da peça com o vídeo curto do anúncio (RN-48), um por peça. Aceita
nulo: o vídeo é opcional, e as peças gravadas antes desta coluna não têm.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c8f3b1e5d2a4"
down_revision: Union[str, None] = "b5e2a8d4c7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("video_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "video_url")
