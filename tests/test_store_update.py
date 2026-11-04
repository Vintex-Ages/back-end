"""O vendedor edita a própria loja: `PATCH /api/users/me/store` (back-end#221)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.address import Address
from app.models.store import Store
from app.repositories.store_repository import StoreRepository
from tests.conftest import TestingSessionLocal

LOGO = "https://cdn.vintex.test/api/media/stores/logos/abc"
ENDERECO = {
    "street": "Rua Ali",
    "number": "120",
    "complement": None,
    "neighborhood": "Centro",
    "city": "Porto Alegre",
    "state": "rs",
    "zip_code": "90010000",
}


def _vendedora(client: TestClient, email: str = "loja@vintex.com", **loja) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"name": "Vendedora", "email": email, "password": "senha123"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    corpo = {
        "name": "Brechó Aurora",
        "description": "Peças dos anos 90",
        "pix_key": "aurora@vintex.com",
        "document_type": "CPF",
        "document_value": "52998224725",
        **loja,
    }
    criada = client.post("/api/users/me/store", json=corpo, headers=headers)
    assert criada.status_code == 201, criada.text
    return headers


def test_altera_so_a_logo(client: TestClient) -> None:
    """Loja criada sem logo passa a poder ter uma, e o resto fica igual."""
    headers = _vendedora(client)
    antes = client.get("/api/users/me/store", headers=headers).json()
    assert antes["logo_url"] is None

    r = client.patch("/api/users/me/store", json={"logo_url": LOGO}, headers=headers)

    assert r.status_code == 200, r.text
    depois = r.json()
    assert depois["logo_url"] == LOGO
    assert {k: v for k, v in depois.items() if k != "logo_url"} == {
        k: v for k, v in antes.items() if k != "logo_url"
    }


def test_logo_nula_tira_a_logo(client: TestClient) -> None:
    headers = _vendedora(client, logo_url=LOGO)

    r = client.patch("/api/users/me/store", json={"logo_url": None}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["logo_url"] is None


def test_altera_nome_descricao_e_chave_pix(client: TestClient) -> None:
    headers = _vendedora(client)

    r = client.patch(
        "/api/users/me/store",
        json={
            "name": "Brechó Aurora Vintage",
            "description": "Agora com peças dos anos 80",
            "pix_key": "pix@aurora.com",
        },
        headers=headers,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Brechó Aurora Vintage"
    assert body["description"] == "Agora com peças dos anos 80"
    assert body["pix_key"] == "pix@aurora.com"


def test_altera_o_endereco(client: TestClient, db_session) -> None:
    headers = _vendedora(client, address=ENDERECO)

    r = client.patch(
        "/api/users/me/store",
        json={"address": {**ENDERECO, "city": "Pelotas", "zip_code": "96010000"}},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    endereco = r.json()["address"]
    assert endereco["city"] == "Pelotas"
    assert endereco["zip_code"] == "96010000"
    assert endereco["state"] == "RS"
    # Reaproveita a linha do endereço: editar não deixa endereço órfão.
    assert db_session.query(Address).count() == 1


def test_endereco_novo_em_loja_que_nao_tinha(client: TestClient) -> None:
    headers = _vendedora(client)

    r = client.patch("/api/users/me/store", json={"address": ENDERECO}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["address"]["street"] == "Rua Ali"
    loja_id = r.json()["id"]
    assert client.get(f"/api/stores/{loja_id}").json()["address"]["city"] == (
        "Porto Alegre"
    )


def test_corpo_vazio_nao_muda_nada(client: TestClient) -> None:
    headers = _vendedora(client, logo_url=LOGO, address=ENDERECO)
    antes = client.get("/api/users/me/store", headers=headers).json()

    r = client.patch("/api/users/me/store", json={}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json() == antes


def test_documento_nao_e_alteravel_por_aqui(client: TestClient) -> None:
    headers = _vendedora(client)

    r = client.patch(
        "/api/users/me/store",
        json={"document_type": "CNPJ", "document_value": "11222333000181"},
        headers=headers,
    )

    assert r.status_code == 422
    loja = client.get("/api/users/me/store", headers=headers).json()
    assert loja["document_type"] == "CPF"
    assert loja["document_value"] == "52998224725"


def test_nome_nulo_e_recusado(client: TestClient) -> None:
    headers = _vendedora(client)

    r = client.patch("/api/users/me/store", json={"name": None}, headers=headers)

    assert r.status_code == 422


def test_sem_loja_responde_404(client: TestClient) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "name": "Comprador",
            "email": "sem-loja@vintex.com",
            "password": "x1234567",
        },
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    resposta = client.patch("/api/users/me/store", json={"name": "X"}, headers=headers)

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_sem_token_responde_401(client: TestClient) -> None:
    assert client.patch("/api/users/me/store", json={}).status_code == 401


def test_repository_nao_commita(db_session) -> None:
    """ADR 0001 §6: quem fecha a transação é o controller. Desfeita a
    transação, a loja salva pelo repository não fica no banco."""
    repository = StoreRepository(db_session)

    store = repository.save(Store(seller_id=1, name="Loja que não fica"))
    assert store.id is not None
    db_session.rollback()

    outra_sessao = TestingSessionLocal()
    try:
        assert (
            outra_sessao.query(Store).filter_by(name="Loja que não fica").count() == 0
        )
    finally:
        outra_sessao.close()
