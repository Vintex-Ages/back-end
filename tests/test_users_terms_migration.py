"""Migration da versão dos termos em `users` (back-end#259).

Roda contra o banco migrado pelo Alembic, e não pelo `create_all`: é a
migration que está sendo testada.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

RAIZ = Path(__file__).resolve().parents[1]
REVISAO_ANTERIOR = "cfc160831d43"
COLUNAS = {"terms_version", "terms_accepted_at"}


def _alembic(comando: str, revisao: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", comando, revisao],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": os.environ["TEST_POSTGRES_URL"]},
        check=True,
    )


def _colunas_de_users(pg_engine: Engine) -> set[str]:
    with pg_engine.connect() as conn:
        return {coluna["name"] for coluna in inspect(conn).get_columns("users")}


@pytest.mark.postgres
@pytest.mark.skipif(
    os.environ.get("TEST_POSTGRES_REUSE_MIGRATED_DB") == "1",
    reason="desce migration: só roda em banco de teste descartável",
)
def test_migration_desce_e_sobe_com_usuario_antigo(pg_engine: Engine) -> None:
    """Desce e sobe com um usuário que já existia. Ele sobrevive às duas
    direções e volta com a versão vazia, que é o caso de quem se cadastrou
    antes da back-end#259."""
    with pg_engine.begin() as conn:
        user_id = conn.scalar(
            text(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES ('Antiga', 'antiga.migra@test.local', 'x') RETURNING id"
            )
        )
    pg_engine.dispose()

    try:
        _alembic("downgrade", REVISAO_ANTERIOR)
        assert _colunas_de_users(pg_engine).isdisjoint(COLUNAS)

        _alembic("upgrade", "head")
        assert COLUNAS <= _colunas_de_users(pg_engine)
        with pg_engine.connect() as conn:
            versao, aceito_em = conn.execute(
                text(
                    "SELECT terms_version, terms_accepted_at FROM users "
                    "WHERE id = :id"
                ),
                {"id": user_id},
            ).one()
        assert versao is None
        assert aceito_em is None
    finally:
        pg_engine.dispose()
        _alembic("upgrade", "head")
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
