# GET e PUT /api/users/me/preferences (#80). Contrato espelhado no front em
# front-end#287: envelope `{ "preferences": [...] }` nos dois sentidos.

import pytest

from app.models.user_preference import UserPreference
from app.schemas.user_schema import MAX_PREFERENCES

ROTA_REGISTER = "/api/auth/register"
ROTA = "/api/users/me/preferences"


def _auth(client, email="pref@example.com"):
    response = client.post(
        ROTA_REGISTER,
        json={"name": "Usuária Pref", "email": email, "password": "Senha123"},
    )
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['access_token']}"}


def _put(client, headers, preferences):
    return client.put(ROTA, json={"preferences": preferences}, headers=headers)


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_sem_token_retorna_401(client, metodo):
    kwargs = {"json": {"preferences": []}} if metodo == "put" else {}
    response = getattr(client, metodo)(ROTA, **kwargs)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_get_sem_preferencias_retorna_lista_vazia(client):
    _, headers = _auth(client)

    response = client.get(ROTA, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"preferences": []}


def test_put_grava_e_get_devolve_na_mesma_ordem(client):
    _, headers = _auth(client)
    prefs = [
        {"type": "estilo", "value": "y2k"},
        {"type": "estilo", "value": "streetwear"},
    ]

    response = _put(client, headers, prefs)

    assert response.status_code == 200
    assert response.json() == {"preferences": prefs}
    assert client.get(ROTA, headers=headers).json() == {"preferences": prefs}


def test_put_substitui_o_conjunto_anterior(client, db_session):
    user_id, headers = _auth(client)
    _put(client, headers, [{"type": "estilo", "value": "y2k"}])

    nova = [
        {"type": "estilo", "value": "alfaiataria"},
        {"type": "estilo", "value": "gotico-dark"},
    ]
    response = _put(client, headers, nova)

    assert response.status_code == 200
    assert client.get(ROTA, headers=headers).json() == {"preferences": nova}
    total = db_session.query(UserPreference).filter_by(user_id=user_id).count()
    assert total == 2


def test_put_mantendo_item_que_ja_existia_nao_viola_unique(client):
    _, headers = _auth(client)
    _put(client, headers, [{"type": "estilo", "value": "y2k"}])

    prefs = [
        {"type": "estilo", "value": "y2k"},
        {"type": "estilo", "value": "boho-romantico"},
    ]
    response = _put(client, headers, prefs)

    assert response.status_code == 200
    assert response.json() == {"preferences": prefs}


def test_put_e_idempotente(client):
    _, headers = _auth(client)
    prefs = [{"type": "estilo", "value": "streetwear"}]

    primeira = _put(client, headers, prefs)
    segunda = _put(client, headers, prefs)

    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json() == segunda.json() == {"preferences": prefs}


def test_put_com_lista_vazia_limpa_o_perfil(client, db_session):
    user_id, headers = _auth(client)
    _put(client, headers, [{"type": "estilo", "value": "y2k"}])

    response = _put(client, headers, [])

    assert response.status_code == 200
    assert response.json() == {"preferences": []}
    assert db_session.query(UserPreference).filter_by(user_id=user_id).count() == 0


def test_put_com_item_repetido_grava_uma_vez(client):
    _, headers = _auth(client)
    item = {"type": "estilo", "value": "y2k"}

    response = _put(client, headers, [item, item])

    assert response.status_code == 200
    assert response.json() == {"preferences": [item]}


def test_put_remove_espacos_das_pontas(client):
    _, headers = _auth(client)

    response = _put(client, headers, [{"type": " estilo ", "value": " y2k "}])

    assert response.json() == {"preferences": [{"type": "estilo", "value": "y2k"}]}


def test_preferencias_de_um_usuario_nao_afetam_outro(client):
    _, headers_a = _auth(client, email="a@example.com")
    _, headers_b = _auth(client, email="b@example.com")
    _put(client, headers_a, [{"type": "estilo", "value": "y2k"}])

    _put(client, headers_b, [])

    assert client.get(ROTA, headers=headers_a).json() == {
        "preferences": [{"type": "estilo", "value": "y2k"}]
    }
    assert client.get(ROTA, headers=headers_b).json() == {"preferences": []}


@pytest.mark.parametrize(
    "corpo",
    [
        [{"type": "estilo", "value": "y2k"}],  # array cru, sem envelope
        {},
        {"preferences": [{"type": "estilo"}]},
        {"preferences": [{"type": "estilo", "value": "   "}]},
        {"preferences": [{"type": "", "value": "y2k"}]},
        {"preferences": [{"type": "x" * 51, "value": "y2k"}]},
        {"preferences": [{"type": "estilo", "value": "x" * 101}]},
        {
            "preferences": [
                {"type": "estilo", "value": f"v{i}"} for i in range(MAX_PREFERENCES + 1)
            ]
        },
    ],
)
def test_put_com_corpo_invalido_retorna_422_e_nao_altera(client, corpo):
    _, headers = _auth(client)
    prefs = [{"type": "estilo", "value": "y2k"}]
    _put(client, headers, prefs)

    response = client.put(ROTA, json=corpo, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(ROTA, headers=headers).json() == {"preferences": prefs}


def test_rotas_documentadas_no_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert {"get", "put"} <= set(paths[ROTA])
