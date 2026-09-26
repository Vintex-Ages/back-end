import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite://"
os.environ.setdefault("DATABASE_URL", SQLALCHEMY_DATABASE_URL)

RAIZ = Path(__file__).resolve().parents[1]

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

import app.models  # noqa: E402,F401 - ensures models register on Base.metadata
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if TEST_POSTGRES_URL:
        return
    pular = pytest.mark.skip(
        reason="exige PostgreSQL: defina TEST_POSTGRES_URL para rodar"
    )
    for item in items:
        if item.get_closest_marker("postgres"):
            item.add_marker(pular)


def _rodar_alembic(comando: str, revisao: str, url: str) -> None:
    """Aplica ou desfaz as migrations num processo separado.

    O `alembic/env.py` sempre sobrescreve a URL com `settings.DATABASE_URL`,
    que neste processo ja nasceu como SQLite. Um subprocesso com a variavel
    de ambiente propria e o mesmo caminho usado pelo job `Migrations` do CI.
    """
    subprocess.run(
        [sys.executable, "-m", "alembic", comando, revisao],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
    )


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    if not TEST_POSTGRES_URL:
        pytest.skip("exige PostgreSQL: defina TEST_POSTGRES_URL para rodar")

    nome_do_banco = (make_url(TEST_POSTGRES_URL).database or "").lower()
    if not nome_do_banco.endswith("_test"):
        pytest.fail(
            f"TEST_POSTGRES_URL aponta para o banco '{nome_do_banco}'. "
            "Use um banco cujo nome termine em '_test': esta fixture apaga todas as tabelas."
        )

    _rodar_alembic("upgrade", "head", TEST_POSTGRES_URL)
    pg = create_engine(TEST_POSTGRES_URL)
    yield pg
    pg.dispose()
    _rodar_alembic("downgrade", "base", TEST_POSTGRES_URL)


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def pg_client(pg_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield pg_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
