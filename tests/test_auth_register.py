# POST /api/auth/register — cadastro de comprador (#77, #78).

import pytest

from app.controllers.auth_controller import AuthController
from app.core.errors import Conflict
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth_schema import RegisterRequest

ROTA = "/api/auth/register"


def _payload(**overrides):
    data = {
        "name": "Nova Compradora",
        "email": "nova@example.com",
        "password": "Senha123",
    }
    data.update(overrides)
    return data


def test_cadastro_com_dados_validos_retorna_201_com_usuario_e_token(client):
    response = client.post(ROTA, json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "Nova Compradora"
    assert body["user"]["email"] == "nova@example.com"
    assert body["user"]["is_admin"] is False
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_cadastro_sem_cpf_conclui_normalmente(client):
    # RN-28: cadastro de comprador não pede CPF.
    response = client.post(ROTA, json=_payload())
    assert response.status_code == 201


def test_cadastro_com_nome_vazio_retorna_422(client):
    response = client.post(ROTA, json=_payload(name=""))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in body["error"]["fields"]


def test_cadastro_com_nome_so_espacos_retorna_422(client):
    response = client.post(ROTA, json=_payload(name="   "))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in body["error"]["fields"]


def test_cadastro_com_nome_maior_que_120_retorna_422(client):
    response = client.post(ROTA, json=_payload(name="A" * 121))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in body["error"]["fields"]


def test_cadastro_com_nome_com_espacos_nas_bordas_e_normalizado(client, db_session):
    response = client.post(ROTA, json=_payload(name="  Nova Compradora  "))

    assert response.status_code == 201
    assert response.json()["user"]["name"] == "Nova Compradora"

    user = db_session.query(User).filter_by(email="nova@example.com").one()
    assert user.name == "Nova Compradora"


def test_cadastro_com_email_invalido_retorna_422(client):
    response = client.post(ROTA, json=_payload(email="invalido.com"))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "email" in body["error"]["fields"]


def test_cadastro_com_senha_curta_retorna_422(client):
    response = client.post(ROTA, json=_payload(password="123"))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "password" in body["error"]["fields"]


def test_cadastro_com_senha_sem_numero_retorna_422(client):
    response = client.post(ROTA, json=_payload(password="somenteletras"))
    assert response.status_code == 422
    assert "password" in response.json()["error"]["fields"]


def test_cadastro_com_email_repetido_retorna_409(client):
    client.post(ROTA, json=_payload(email="repetido@example.com"))

    response = client.post(ROTA, json=_payload(email="repetido@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_senha_e_persistida_como_hash_nao_texto_puro(client, db_session):
    client.post(ROTA, json=_payload(email="hash-check@example.com"))

    user = db_session.query(User).filter_by(email="hash-check@example.com").one()
    assert user.password_hash != "Senha123"


def test_email_e_normalizado_para_minusculas(client, db_session):
    client.post(ROTA, json=_payload(email="Maiuscula@Example.COM"))

    user = db_session.query(User).filter_by(email="maiuscula@example.com").one()
    assert user.email == "maiuscula@example.com"


def test_email_repetido_com_caixa_diferente_retorna_409(client):
    client.post(ROTA, json=_payload(email="mesmo@example.com"))

    response = client.post(ROTA, json=_payload(email="MESMO@EXAMPLE.COM"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_cadastro_com_corrida_na_unicidade_retorna_409_nao_500(db_session, monkeypatch):
    # Simula a janela de corrida: outro cadastro com o mesmo e-mail já
    # comitou, mas o "check rápido" (get_by_email) ainda não o enxerga.
    existing = User(
        name="Já existe",
        email="corrida@example.com",
        password_hash=hash_password("Senha123"),
    )
    db_session.add(existing)
    db_session.commit()

    controller = AuthController(db_session)
    monkeypatch.setattr(controller.repository, "get_by_email", lambda email: None)
    data = RegisterRequest(
        name="Corrida", email="corrida@example.com", password="Senha123"
    )

    with pytest.raises(Conflict) as exc_info:
        controller.register(data)

    assert exc_info.value.code == "EMAIL_TAKEN"


def test_cadastro_grava_a_versao_dos_termos_aceita(client, db_session):
    """RN-93: os termos são versionados, e o aceite precisa dizer qual versão a
    pessoa aceitou, não só que aceitou (back-end#259)."""
    response = client.post(ROTA, json=_payload(accepted_terms_version="2026-09"))

    assert response.status_code == 201
    user = db_session.query(User).filter_by(email="nova@example.com").one()
    assert user.terms_version == "2026-09"
    assert user.terms_accepted_at is not None


def test_cadastro_sem_versao_dos_termos_nao_grava_data_de_aceite(client, db_session):
    """Data sem versão registraria um aceite que ninguém deu: sem versão, as
    duas colunas ficam vazias, como no cadastro da loja."""
    response = client.post(ROTA, json=_payload())

    assert response.status_code == 201
    user = db_session.query(User).filter_by(email="nova@example.com").one()
    assert user.terms_version is None
    assert user.terms_accepted_at is None


def test_versao_dos_termos_vazia_ou_longa_demais_retorna_422(client):
    for versao in ("", "v" * 21):
        response = client.post(ROTA, json=_payload(accepted_terms_version=versao))
        assert response.status_code == 422, versao


def test_usuario_cadastrado_antes_da_versao_dos_termos_continua_entrando(
    client, db_session
):
    """Quem se cadastrou antes da back-end#259 não tem versão gravada. A
    leitura desse usuário não pode quebrar: login e `/users/me` seguem 200."""
    antigo = User(
        name="Antiga",
        email="antiga@example.com",
        password_hash=hash_password("Senha123"),
    )
    db_session.add(antigo)
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": "antiga@example.com", "password": "Senha123"},
    )
    assert login.status_code == 200
    me = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert antigo.terms_version is None
