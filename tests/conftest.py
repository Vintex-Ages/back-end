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
TEST_POSTGRES_REUSE_MIGRATED_DB = (
    os.environ.get("TEST_POSTGRES_REUSE_MIGRATED_DB") == "1"
)

import app.models  # noqa: E402,F401 - ensures models register on Base.metadata
from app.core.security import create_access_token  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


def _auth_headers(user_id: int, *, is_admin: bool = False) -> dict[str, str]:
    """Cabeçalho de sessão real para o usuário.

    Substitui o `X-User-Id` que as rotas da Sprint 2 usavam antes da `#151`. O
    usuário precisa existir no banco: `get_current_user` resolve o token e vai
    buscá-lo, e um id que não existe responde 401.
    """
    return {"Authorization": f"Bearer {create_access_token(user_id, is_admin)}"}


@pytest.fixture
def usuario_sem_loja(db_session):
    """Usuário logado que não é vendedor.

    Antes da `#151` bastava mandar um id qualquer no cabeçalho, inclusive um que
    não existia. Agora o token é resolvido contra o banco, então um usuário de
    verdade precisa existir para que a resposta seja "você não tem loja" e não
    "você não está autenticado".
    """
    from app.models.user import User

    user = User(
        name="Sem loja",
        email="sem.loja@test.local",
        password_hash="not-a-real-password",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers():
    """Entrega `_auth_headers` aos testes.

    Fixture e não import: `tests/` não é pacote e `from conftest import ...` não
    resolve com o `importmode` deste repositório.
    """
    return _auth_headers


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

    if not TEST_POSTGRES_REUSE_MIGRATED_DB:
        nome_do_banco = (make_url(TEST_POSTGRES_URL).database or "").lower()
        if not nome_do_banco.endswith("_test"):
            pytest.fail(
                f"TEST_POSTGRES_URL aponta para o banco '{nome_do_banco}'. "
                "Use um banco cujo nome termine em '_test': esta fixture apaga "
                "todas as tabelas."
            )
        _rodar_alembic("upgrade", "head", TEST_POSTGRES_URL)

    pg = create_engine(TEST_POSTGRES_URL)
    try:
        yield pg
    finally:
        pg.dispose()
        if not TEST_POSTGRES_REUSE_MIGRATED_DB:
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
