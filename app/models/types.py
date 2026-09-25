"""Tipos de coluna compartilhados entre models (BE-US027-1, back-end#92).

`EmbeddingVector` é `vector(dim)` de verdade no Postgres (via `pgvector`,
usado pelo índice de similaridade) e cai para `JSON` em qualquer outro
dialeto — hoje só o SQLite dos testes. Isso evita depender de Postgres para
rodar a suíte (a #139/PR #161 cobre isso de forma mais geral; enquanto não
mergeia, esta é a saída mínima para este model não quebrar os outros 13
arquivos de teste).
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
