# GET /api/users/me (#84). Substitui GET /api/auth/me — ver ADR 0001 §4 e a
# nota em app/views/user_routes.py.

from app.models.seller import Seller

ROTA_REGISTER = "/api/auth/register"
ROTA_ME = "/api/users/me"


def _registrar(client, email="me@example.com"):
    response = client.post(
        ROTA_REGISTER,
        json={"name": "Usuária Me", "email": email, "password": "Senha123"},
    )
    return response.json()


def test_me_sem_token_retorna_401(client):
    response = client.get(ROTA_ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_me_comprador_sem_vendedor_retorna_is_seller_falso(client):
    auth = _registrar(client)

    response = client.get(
        ROTA_ME, headers={"Authorization": f"Bearer {auth['access_token']}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == auth["user"]["id"]
    assert body["email"] == auth["user"]["email"]
    assert body["is_admin"] is False
    assert body["is_seller"] is False


def test_me_com_vendedor_associado_retorna_is_seller_verdadeiro(client, db_session):
    auth = _registrar(client, email="vendedora-me@example.com")

    seller = Seller(
        user_id=auth["user"]["id"],
        document_type="CPF",
        document_value="987.654.321-00",
    )
    db_session.add(seller)
    db_session.commit()

    response = client.get(
        ROTA_ME, headers={"Authorization": f"Bearer {auth['access_token']}"}
    )

    assert response.status_code == 200
    assert response.json()["is_seller"] is True
