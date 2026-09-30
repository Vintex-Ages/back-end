"""add product sold_at

Revision ID: a7c91e4b5d02
Revises: d3f8a1b2c4e6
Create Date: 2026-09-30

Coluna da data da venda (back-end#146). Sem ela não existe "no período": a
data de última alteração muda a cada edição e não serve.

Nullable de propósito. Peça vendida antes desta migration não tem data, e
inventar uma seria fabricar histórico. O que a migration faz é preencher as
peças **sintéticas** do seed, que é o único lugar onde peça vira vendida nesta
sprint (não há checkout), uma a cada seis dias contados de hoje para trás — o
mesmo espaçamento de `app/seeds/pecas.py::_sold_at_for`. Sem espalhar, os três
períodos da tela mostram o mesmo valor e o seletor parece quebrado.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c91e4b5d02"
down_revision: Union[str, None] = "d3f8a1b2c4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("sold_at", sa.DateTime(), nullable=True))
    op.create_index("ix_products_sold_at", "products", ["sold_at"])
    op.execute(
        """
        WITH ordenadas AS (
            SELECT id, (row_number() OVER (ORDER BY id) - 1) * 6 AS dias
              FROM products
             WHERE status = 'vendido'
               AND sold_at IS NULL
        )
        UPDATE products AS p
           SET sold_at = (now() AT TIME ZONE 'utc')
                       - make_interval(days => ordenadas.dias::int)
          FROM ordenadas
         WHERE p.id = ordenadas.id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_products_sold_at", table_name="products")
    op.drop_column("products", "sold_at")
