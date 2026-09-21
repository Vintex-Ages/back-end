import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite://"
os.environ.setdefault("DATABASE_URL", SQLALCHEMY_DATABASE_URL)

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


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    if not TEST_POSTGRES_URL:
        pytest.skip("exige PostgreSQL: defina TEST_POSTGRES_URL para rodar")

    nome_do_banco = make_url(TEST_POSTGRES_URL).database or ""
    if "test" not in nome_do_banco:
        pytest.fail(
            f"TEST_POSTGRES_URL aponta para o banco '{nome_do_banco}'. "
            "Use um banco cujo nome contenha 'test': esta fixture apaga todas as tabelas."
        )

    pg = create_engine(TEST_POSTGRES_URL)
    with pg.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(
            text(
                "CREATE OR REPLACE FUNCTION immutable_unaccent(text) "
                "RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
                "AS $func$ SELECT public.unaccent('public.unaccent', $1) $func$"
            )
        )
    Base.metadata.drop_all(bind=pg)
    Base.metadata.create_all(bind=pg)
    yield pg
    Base.metadata.drop_all(bind=pg)
    pg.dispose()


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
