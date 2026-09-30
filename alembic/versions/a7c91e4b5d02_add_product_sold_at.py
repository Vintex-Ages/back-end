"""add product sold_at

Revision ID: a7c91e4b5d02
Revises: d3f8a1b2c4e6
Create Date: 2026-09-30

Coluna da data da venda (back-end#146). Sem ela não existe "no período": a
data de última alteração muda a cada edição e não serve.

Nullable de propósito: peça vendida antes desta migration não tem data.

O backfill preenche **toda** peça com `status='vendido'` e `sold_at IS NULL`,
uma a cada seis dias contados de hoje para trás. Hoje isso significa só as oito
peças do seed, porque nada nesta sprint transforma peça em vendida — não há
checkout (VS-022, #44) e o seed é o único lugar que grava `'vendido'`. **Mas o
`WHERE` não distingue peça sintética de venda real**, e quando o checkout entrar
esta migration já terá rodado; se alguma venda real aparecer antes, ela recebe
data fabricada. Está escrito aqui porque a versão anterior deste texto prometia
o contrário.

O espaçamento de seis dias é sobre a ordem global das vendidas, e o resumo
financeiro é por loja: com o seed distribuindo peça entre sete lojas, um
vendedor tem uma venda só, e os três períodos da tela mostram o mesmo número.
Isso é a conta certa para quem vendeu uma vez, não um defeito — mas não deixa o
seletor de período informar nada na demonstração.
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
    op.execute("""
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
        """)


def downgrade() -> None:
    op.drop_index("ix_products_sold_at", table_name="products")
    op.drop_column("products", "sold_at")
