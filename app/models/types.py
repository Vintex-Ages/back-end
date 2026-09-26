"""Tipos de coluna compartilhados entre models (BE-US027-1, back-end#92).

`EmbeddingVector` é `vector(dim)` de verdade no Postgres (via `pgvector`,
usado pelo índice de similaridade) e cai para `JSON` em qualquer outro
dialeto — hoje só o SQLite dos testes.

A #139/PR #161 (mergeada) **não substitui isso**: ela só deixa testes
marcados com `@pytest.mark.postgres` rodarem contra um Postgres real quando
`TEST_POSTGRES_URL` está definido, pulando-os quando não está. Os fixtures
padrão (`db_session`/`client`, usados pelos outros 13+ arquivos de teste,
incluindo os deste model) continuam em SQLite por padrão — e sem este
fallback, `Base.metadata.create_all()` quebraria todos eles assim que
`Product.embedding` entrasse no model.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy.types import JSON, TypeDecorator


class EmbeddingVector(TypeDecorator):
    # `none_as_null`: sem isso, o JSON do SQLAlchemy grava `None` como o
    # literal JSON `null`, não como `NULL` de verdade — e toda consulta
    # `embedding IS NULL` (base do backfill idempotente) deixa de bater.
    impl = JSON(none_as_null=True)
    cache_ok = True

    def __init__(self, dim: int, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.dim = dim

    # `.cosine_distance()`/`.l2_distance()` (BE-US027-3, back-end#149): sem
    # isso, `Product.embedding.cosine_distance(...)` não existe — o
    # TypeDecorator não herda o comparator do `impl` sozinho. Só faz sentido
    # chamar isso contra Postgres (o comparador ainda existiria no SQLite,
    # mas geraria SQL inválido — os testes de busca por similaridade usam a
    # fixture `pg_session`, nunca o SQLite).
    comparator_factory = Vector.comparator_factory

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON(none_as_null=True))

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return list(value)
