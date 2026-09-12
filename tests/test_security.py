# Testes de app/core/security.py — hash de senha, token JWT e as dependencies
# de autorização (get_current_user, require_auth, require_seller,
# require_admin, optional_user). Ver .ai/adr/0002-autenticacao-jwt.md.
#
# BE-FND-3 não expõe endpoint próprio: as dependencies são exercitadas por um
# app FastAPI de teste, isolado do app real, com rotas mínimas.

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    optional_user,
    require_admin,
    require_auth,
    require_seller,
    verify_password,
)
from app.database import get_db
from app.models import Seller, User


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protegida")
    def protegida(user: User = Depends(require_auth)):
        return {"id": user.id}

    @app.get("/vendedor")
    def vendedor(user: User = Depends(require_seller)):
        return {"id": user.id}

    @app.get("/admin")
    def admin(user: User = Depends(require_admin)):
        return {"id": user.id}

    @app.get("/publica")
    def publica(user: User | None = Depends(optional_user)):
        return {"autenticado": user is not None}

    @app.get("/quem-sou")
    def quem_sou(user: User = Depends(get_current_user)):
        return {"id": user.id, "email": user.email}

    return app


@pytest.fixture
def security_client(db_session):
    app = _build_test_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


def _criar_usuario(db_session, **overrides) -> User:
    defaults = {
        "name": "Compradora Teste",
        "email": "compradora@example.com",
        "password_hash": hash_password("Senha123"),
        "is_admin": False,
    }
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _token_para(user: User) -> str:
    return create_access_token(user.id, user.is_admin)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- hash / verificação de senha -------------------------------------------------


def test_hash_password_nao_e_o_texto_puro():
    assert hash_password("Senha123") != "Senha123"


def test_verify_password_credenciais_corretas():
    h = hash_password("Senha123")
    assert verify_password("Senha123", h) is True


def test_verify_password_credenciais_erradas():
    h = hash_password("Senha123")
    assert verify_password("outra-senha", h) is False


def test_verify_password_hash_invalido_nunca_autentica():
    # sentinela gravado pelo seed (app/seeds/lojas.py) — nunca deve autenticar.
    assert verify_password("qualquer-coisa", "!seed-no-login") is False


# --- require_auth / get_current_user ---------------------------------------------


def test_require_auth_sem_token_retorna_401(security_client):
    response = security_client.get("/protegida")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_require_auth_com_token_valido_retorna_200(security_client, db_session):
    user = _criar_usuario(db_session)
    response = security_client.get(
        "/protegida", headers=_auth_header(_token_para(user))
    )
    assert response.status_code == 200
    assert response.json() == {"id": user.id}


def test_require_auth_token_invalido_retorna_401(security_client):
    response = security_client.get(
        "/protegida", headers=_auth_header("token.invalido.aqui")
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_get_current_user_expoe_dados_do_usuario(security_client, db_session):
    user = _criar_usuario(db_session, email="quemsou@example.com")
    response = security_client.get("/quem-sou", headers=_auth_header(_token_para(user)))
    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": "quemsou@example.com"}


# --- require_seller ---------------------------------------------------------------


def test_require_seller_sem_cadastro_de_vendedor_retorna_403(
    security_client, db_session
):
    user = _criar_usuario(db_session, email="so-comprador@example.com")
    response = security_client.get("/vendedor", headers=_auth_header(_token_para(user)))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_require_seller_com_cadastro_de_vendedor_retorna_200(
    security_client, db_session
):
    user = _criar_usuario(db_session, email="vendedora@example.com")
    seller = Seller(
        user_id=user.id, document_type="CPF", document_value="123.456.789-00"
    )
    db_session.add(seller)
    db_session.commit()

    response = security_client.get("/vendedor", headers=_auth_header(_token_para(user)))
    assert response.status_code == 200
    assert response.json() == {"id": user.id}


def test_require_seller_sem_token_retorna_401(security_client):
    response = security_client.get("/vendedor")
    assert response.status_code == 401


# --- require_admin -----------------------------------------------------------------


def test_require_admin_sem_flag_retorna_403(security_client, db_session):
    user = _criar_usuario(db_session, email="usuario-comum@example.com", is_admin=False)
    response = security_client.get("/admin", headers=_auth_header(_token_para(user)))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_require_admin_com_flag_retorna_200(security_client, db_session):
    user = _criar_usuario(db_session, email="admin@example.com", is_admin=True)
    response = security_client.get("/admin", headers=_auth_header(_token_para(user)))
    assert response.status_code == 200
    assert response.json() == {"id": user.id}


# --- optional_user (rotas públicas) -------------------------------------------------


def test_optional_user_sem_token_funciona_como_anonimo(security_client):
    response = security_client.get("/publica")
    assert response.status_code == 200
    assert response.json() == {"autenticado": False}


def test_optional_user_com_token_valido_reconhece_usuario(security_client, db_session):
    user = _criar_usuario(db_session, email="visitante-logado@example.com")
    response = security_client.get("/publica", headers=_auth_header(_token_para(user)))
    assert response.status_code == 200
    assert response.json() == {"autenticado": True}


def test_optional_user_token_invalido_nao_quebra_rota_publica(security_client):
    # RN-26: uma rota pública nunca pode falhar por causa de um token velho/ruim.
    response = security_client.get(
        "/publica", headers=_auth_header("token.invalido.aqui")
    )
    assert response.status_code == 200
    assert response.json() == {"autenticado": False}
