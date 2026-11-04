# Guarda de administradora nas rotas de `/api/admin` e conta no seed (back-end#61).
#
# Ainda não existe rota de administração: a fila de comprovantes (#250) e o
# aprovar/rejeitar (#251) chegam depois. A matriz roda contra uma rota de teste
# montada com as MESMAS `dependencies` do router real, e um segundo teste
# confere no app real que toda rota sob `/api/admin` passa pela guarda.

import re

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.core.errors import register_exception_handlers
from app.core.security import create_access_token, hash_password, require_admin
from app.database import get_db
from app.main import app as app_real
from app.models import Seller, User
from app.seeds import admin as seed
from app.views.admin_routes import router as admin_router


@pytest.fixture
def admin_client(db_session):
    sonda = APIRouter()

    @sonda.get("/sonda")
    def rota_de_admin() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        sonda, prefix="/api/admin", dependencies=admin_router.dependencies
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


def _usuario(db_session, email: str, *, is_admin: bool = False) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash=hash_password("Senha123"),
        is_admin=is_admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _token(user: User, *, is_admin: bool | None = None) -> dict[str, str]:
    claim = user.is_admin if is_admin is None else is_admin
    return {"Authorization": f"Bearer {create_access_token(user.id, claim)}"}


# --- matriz de papel -------------------------------------------------------------


def test_sem_sessao_responde_401(admin_client):
    response = admin_client.get("/api/admin/sonda")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_comprador_responde_403_com_codigo_proprio(admin_client, db_session):
    comprador = _usuario(db_session, "comprador@test.local")

    response = admin_client.get("/api/admin/sonda", headers=_token(comprador))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_vendedor_responde_403(admin_client, db_session):
    vendedora = _usuario(db_session, "vendedora@test.local")
    db_session.add(
        Seller(user_id=vendedora.id, document_type="CPF", document_value="52998224725")
    )
    db_session.commit()

    response = admin_client.get("/api/admin/sonda", headers=_token(vendedora))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_administradora_responde_200(admin_client, db_session):
    admin = _usuario(db_session, "admin@test.local", is_admin=True)

    response = admin_client.get("/api/admin/sonda", headers=_token(admin))

    assert response.status_code == 200


def test_claim_is_admin_do_token_nao_basta(admin_client, db_session):
    """O papel vem do banco. Token com `is_admin=true` de quem não é admin no
    banco (papel retirado depois do login, por exemplo) responde 403."""
    comprador = _usuario(db_session, "ex-admin@test.local")

    response = admin_client.get(
        "/api/admin/sonda", headers=_token(comprador, is_admin=True)
    )

    assert response.status_code == 403


def _rotas_de_admin() -> list[tuple[str, str]]:
    """(método, caminho) de toda rota sob `/api/admin` no app real.

    Lido do OpenAPI, que é API pública: `app.routes` nesta versão do FastAPI
    guarda os routers incluídos sem achatar, e o teste não enxergava nada.
    """
    caminhos = app_real.openapi()["paths"]
    return [
        (metodo.upper(), re.sub(r"\{[^}]+\}", "1", caminho))
        for caminho, operacoes in caminhos.items()
        if caminho.startswith("/api/admin")
        for metodo in operacoes
    ]


def test_toda_rota_de_admin_do_app_exige_a_administradora(client, db_session):
    """Vale para as rotas que a #250 e a #251 vão criar: uma rota em
    `/api/admin` que não passe pela guarda quebra este teste."""
    comprador = _usuario(db_session, "comprador-matriz@test.local")

    for metodo, caminho in _rotas_de_admin():
        sem_sessao = client.request(metodo, caminho)
        assert sem_sessao.status_code == 401, (metodo, caminho)

        de_comprador = client.request(metodo, caminho, headers=_token(comprador))
        assert de_comprador.status_code == 403, (metodo, caminho)
        assert de_comprador.json()["error"]["code"] == "ADMIN_REQUIRED"

    assert [d.dependency for d in admin_router.dependencies] == [require_admin]


# --- seed ------------------------------------------------------------------------


def test_seed_cria_a_administradora_e_ela_faz_login(client, db_session):
    seed.seed_admin(db_session)
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": settings.SEED_ADMIN_EMAIL, "password": seed.DEV_ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    me = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.json()["is_admin"] is True


def test_seed_e_idempotente_e_nao_troca_a_senha(db_session):
    primeiro = seed.seed_admin(db_session)
    db_session.commit()
    hash_original = primeiro.password_hash

    segundo = seed.seed_admin(db_session)
    db_session.commit()

    assert segundo.id == primeiro.id
    assert segundo.password_hash == hash_original
    assert (
        db_session.query(User).filter_by(email=settings.SEED_ADMIN_EMAIL).count() == 1
    )


def test_seed_devolve_o_papel_a_conta_existente(db_session):
    conta = _usuario(db_session, settings.SEED_ADMIN_EMAIL)

    seed.seed_admin(db_session)
    db_session.commit()
    db_session.refresh(conta)

    assert conta.is_admin is True


def test_seed_recusa_senha_de_desenvolvimento_em_producao(db_session, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SEED_ADMIN_PASSWORD", "")

    with pytest.raises(RuntimeError, match="SEED_ADMIN_PASSWORD"):
        seed.seed_admin(db_session)


def test_seed_usa_a_senha_do_ambiente(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "SEED_ADMIN_PASSWORD", "senha-do-ambiente")

    seed.seed_admin(db_session)
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": settings.SEED_ADMIN_EMAIL, "password": "senha-do-ambiente"},
    )
    assert response.status_code == 200
