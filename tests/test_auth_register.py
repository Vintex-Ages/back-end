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
