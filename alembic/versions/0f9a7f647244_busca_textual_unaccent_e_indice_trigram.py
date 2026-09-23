"""busca textual: unaccent e indice trigram

Revision ID: 0f9a7f647244
Revises: 42fe2f7c474e
Create Date: 2026-09-09 21:20:00.000000

Escolha: pg_trgm (não tsvector) — a busca da #90 é por presença do termo via
ILIKE, sem ranking nem stemming; o índice GIN de trigramas cobre isso e ainda
tolera termo parcial ("jaque" acha "jaqueta").
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0f9a7f647244"
down_revision: Union[str, None] = "42fe2f7c474e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Concatenação dos quatro campos que a busca cobre (name, description, brand,
# category), normalizada. A #90 consulta com o mesmo `immutable_unaccent(lower(...))`.
_SEARCH_EXPR = (
    "immutable_unaccent(lower("
    "coalesce(name, '') || ' ' || "
    "coalesce(description, '') || ' ' || "
    "coalesce(brand, '') || ' ' || "
    "coalesce(category, '')"
    "))"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # unaccent(text) é STABLE (depende do search_path); um wrapper IMMUTABLE
    # permite usá-lo em índice funcional.
    op.execute("""
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $func$ SELECT public.unaccent('public.unaccent', $1) $func$
        """)

    op.execute(
        f"CREATE INDEX ix_products_search_trgm ON products "
        f"USING gin ({_SEARCH_EXPR} gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_search_trgm")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # As extensões unaccent / pg_trgm permanecem (podem ser usadas por outros).
