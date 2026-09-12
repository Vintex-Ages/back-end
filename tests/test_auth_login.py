# POST /api/auth/login (#82).

ROTA_REGISTER = "/api/auth/register"
ROTA_LOGIN = "/api/auth/login"


def _registrar(client, **overrides):
    data = {
        "name": "Compradora Login",
        "email": "login@example.com",
        "password": "Senha123",
    }
    data.update(overrides)
    return client.post(ROTA_REGISTER, json=data)


def test_login_com_credenciais_corretas_retorna_200_com_token(client):
    _registrar(client)

    response = client.post(
        ROTA_LOGIN, json={"email": "login@example.com", "password": "Senha123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "login@example.com"
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_com_email_inexistente_retorna_401_generico(client):
    response = client.post(
        ROTA_LOGIN, json={"email": "nao-existe@example.com", "password": "Senha123"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_com_senha_errada_retorna_401_com_mesma_mensagem_generica(client):
    _registrar(client, email="senha-errada@example.com")

    resposta_email_errado = client.post(
        ROTA_LOGIN,
        json={"email": "nao-existe-2@example.com", "password": "Senha123"},
    )
    resposta_senha_errada = client.post(
        ROTA_LOGIN,
        json={"email": "senha-errada@example.com", "password": "SenhaErrada1"},
    )

    assert resposta_email_errado.status_code == 401
    assert resposta_senha_errada.status_code == 401
    assert (
        resposta_email_errado.json()["error"]["message"]
        == resposta_senha_errada.json()["error"]["message"]
    )
    assert resposta_senha_errada.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_com_email_inexistente_ainda_roda_verificacao_de_senha(monkeypatch):
    # Contra vazamento de existência de conta por timing: bcrypt deve rodar
    # mesmo sem usuário, contra um hash fictício (ver _HASH_FICTICIO).
    from app.controllers import auth_controller as auth_controller_module

    chamadas = []
    original = auth_controller_module.verify_password

    def espiao(password, password_hash):
        chamadas.append(password_hash)
        return original(password, password_hash)

    monkeypatch.setattr(auth_controller_module, "verify_password", espiao)

    class RepoFalso:
        def get_by_email(self, email):
            return None

    controller = auth_controller_module.AuthController.__new__(
        auth_controller_module.AuthController
    )
    controller.repository = RepoFalso()

    import pytest

    from app.core.errors import Unauthorized
    from app.schemas.auth_schema import LoginRequest

    with pytest.raises(Unauthorized):
        controller.login(
            LoginRequest(email="fantasma@example.com", password="qualquer")
        )

    assert chamadas == [auth_controller_module._HASH_FICTICIO]


def test_login_token_contem_id_e_papel_do_usuario(client):
    import jwt

    from app.config import settings

    _registrar(client, email="payload@example.com")
    response = client.post(
        ROTA_LOGIN, json={"email": "payload@example.com", "password": "Senha123"}
    )

    token = response.json()["access_token"]
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    assert "sub" in payload
    assert "is_admin" in payload
