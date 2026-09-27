"""Disponibilidade da extensão e roundtrip vetorial em PostgreSQL real (#185)."""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

pytestmark = pytest.mark.postgres


def assert_pgvector_roundtrip(connection: Connection) -> None:
    assert connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    )
    connection.execute(
        text(
            "CREATE TEMPORARY TABLE infra_vector_probe (embedding vector(3)) ON COMMIT DROP"
        )
    )
    connection.execute(
        text(
            "INSERT INTO infra_vector_probe (embedding) VALUES (CAST(:embedding AS vector))"
        ),
        {"embedding": "[0.1,0.2,0.3]"},
    )
    assert connection.scalar(
        text("SELECT embedding::text FROM infra_vector_probe")
    ) == ("[0.1,0.2,0.3]")


def test_pgvector_instalado_e_roundtrip(pg_engine: Engine) -> None:
    with pg_engine.begin() as connection:
        assert_pgvector_roundtrip(connection)
