"""Smoke test do PostgreSQL real do Compose vintex-infra (VE-15)."""

import os

import pytest
from sqlalchemy import inspect, text

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.database import engine

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_POSTGRES_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-infra-postgres",
)


def test_postgres_migrado_aceita_gravacao_e_leitura() -> None:
    assert engine.dialect.name == "postgresql"

    expected_heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())

    with engine.begin() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
        assert current_heads == expected_heads and current_heads

        tables = inspect(connection)
        assert tables.has_table("products")
        assert tables.has_table("users")

        connection.execute(
            text(
                "CREATE TEMPORARY TABLE infra_persistence_probe "
                "(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO infra_persistence_probe (id, payload) VALUES (1, :payload)"
            ),
            {"payload": "vintex-infra-postgres"},
        )
        assert (
            connection.scalar(
                text("SELECT payload FROM infra_persistence_probe WHERE id = 1")
            )
            == "vintex-infra-postgres"
        )
