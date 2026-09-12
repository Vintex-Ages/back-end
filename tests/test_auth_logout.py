# POST /api/auth/logout e POST /api/auth/refresh (#83).
#
# JWT é stateless: a sessão persistente entre visitas e o logout real vêm do
# refresh token (ADR 0002, decisão 4) — revogado no logout, rotacionado no
# refresh.

ROTA_REGISTER = "/api/auth/register"
ROTA_LOGIN = "/api/auth/login"
ROTA_LOGOUT = "/api/auth/logout"
ROTA_REFRESH = "/api/auth/refresh"


def _registrar(client, email="sessao@example.com"):
    response = client.post(
        ROTA_REGISTER,
        json={"name": "Usuária Sessão", "email": email, "password": "Senha123"},
    )
    return response.json()


def _auth_header(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def test_logout_com_refresh_token_valido_retorna_204(client):
    auth = _registrar(client)

    response = client.post(
        ROTA_LOGOUT,
        json={"refresh_token": auth["refresh_token"]},
        headers=_auth_header(auth["access_token"]),
    )

    assert response.status_code == 204


def test_logout_sem_token_de_acesso_retorna_401(client):
    auth = _registrar(client, email="sem-access-token@example.com")

    response = client.post(ROTA_LOGOUT, json={"refresh_token": auth["refresh_token"]})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_apos_logout_o_refresh_token_nao_renova_mais_a_sessao(client):
    auth = _registrar(client, email="pos-logout@example.com")

    client.post(
        ROTA_LOGOUT,
        json={"refresh_token": auth["refresh_token"]},
        headers=_auth_header(auth["access_token"]),
    )
    response = client.post(ROTA_REFRESH, json={"refresh_token": auth["refresh_token"]})

    assert response.status_code == 401


def test_refresh_com_token_valido_emite_par_novo_e_revoga_o_antigo(client):
    auth = _registrar(client, email="refresh-ok@example.com")

    response = client.post(ROTA_REFRESH, json={"refresh_token": auth["refresh_token"]})

    assert response.status_code == 200
    novo = response.json()
    # access_token pode coincidir se emitido no mesmo segundo (mesmos claims:
    # sub, is_admin, iat, exp) — não é um problema, ambos são válidos. O que
    # importa é o refresh token: sempre novo, e o antigo nunca mais serve.
    assert novo["refresh_token"] != auth["refresh_token"]

    # o refresh token antigo foi rotacionado: não serve mais.
    reuso = client.post(ROTA_REFRESH, json={"refresh_token": auth["refresh_token"]})
    assert reuso.status_code == 401


def test_refresh_com_token_invalido_retorna_401(client):
    response = client.post(ROTA_REFRESH, json={"refresh_token": "token-que-nao-existe"})
    assert response.status_code == 401


def test_logout_nao_revoga_refresh_token_de_outro_usuario(client):
    auth_a = _registrar(client, email="usuaria-a@example.com")
    auth_b = _registrar(client, email="usuaria-b@example.com")

    # A tenta "deslogar" usando o refresh token de B — nao deve afetar B.
    resposta = client.post(
        ROTA_LOGOUT,
        json={"refresh_token": auth_b["refresh_token"]},
        headers=_auth_header(auth_a["access_token"]),
    )
    assert resposta.status_code == 204

    ainda_funciona = client.post(
        ROTA_REFRESH, json={"refresh_token": auth_b["refresh_token"]}
    )
    assert ainda_funciona.status_code == 200
