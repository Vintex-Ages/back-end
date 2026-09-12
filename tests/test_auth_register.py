# POST /api/auth/register — cadastro de comprador (#77, #78).

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
    from app.models.user import User

    client.post(ROTA, json=_payload(email="hash-check@example.com"))

    user = db_session.query(User).filter_by(email="hash-check@example.com").one()
    assert user.password_hash != "Senha123"
