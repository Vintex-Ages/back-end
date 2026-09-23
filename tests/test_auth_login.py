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


def test_login_com_email_inexistente_delega_para_verify_password_or_dummy(
    monkeypatch,
):
    # Contra vazamento de existência de conta por timing: login() precisa
    # chamar verify_password_or_dummy com password_hash=None (que por sua
    # vez roda o bcrypt contra um hash fictício - testado em
    # test_security.py) em vez de pular a verificação quando não há usuário.
    from app.controllers import auth_controller as auth_controller_module

    chamadas = []

    def espiao(password, password_hash):
        chamadas.append(password_hash)
        return False

    monkeypatch.setattr(auth_controller_module, "verify_password_or_dummy", espiao)

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

    assert chamadas == [None]


def test_login_token_contem_id_e_papel_do_usuario(client):
    import jwt

    from app.config import settings

    _registrar(client, email="payload@example.com")
    response = client.post(
        ROTA_LOGIN, json={"email": "payload@example.com", "password": "Senha123"}
    )

    body = response.json()
    payload = jwt.decode(
        body["access_token"], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    # Verifica o valor, não só a presença: um token emitido para o usuário
    # errado (`_issue_auth_response(outro_user)`) passaria em `"sub" in
    # payload`, mas é exatamente o bug que este teste existe para pegar —
    # é o claim em que toda a autorização da plataforma confia depois.
    assert payload["sub"] == str(body["user"]["id"])
    assert payload["is_admin"] is False
