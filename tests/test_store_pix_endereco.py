"""A loja grava chave Pix e endereco, e nao exige descricao nem versao (#216).

O que estava errado, medido em 28/09 contra o app rodando:

  - `pix_key` e `address` chegavam no corpo, o `StoreCreate` nao os conhecia, e
    `extra="ignore"` fazia a API responder **201** descartando os dois em
    silencio. O formulario do `front-end#212` pede sete campos de endereco mais
    a chave Pix, e nada disso chegava ao banco.
  - `GET /api/stores/{id}` devolvia `"address": null` sempre, embora o
    `StoreDetailResponse` declare o campo e o repository faca
    `joinedload(Store.address)`. Nenhuma rota preenchia `Store.address_id`.
  - `description: ""` dava 422, contra a modelagem, o model e a propria tela.
  - `terms_version` era obrigatorio sem ser validado contra nada.

As fontes de que esses campos sao escopo declarado, e que a #141 omitiu:

  - `vintex-modelagem-1.md` secao 1.4, legenda "NN = not null (obrigatorio)":
    so `seller_id` e `name` tem NN. `description`, `logo_url`, `pix_key` e
    `address_id` nao tem.
  - `VS-006` em Gherkin: "informo CPF ou CNPJ, endereco e chave Pix".
  - `RN-18`, Firme: a chave Pix se registra no cadastro do vendedor.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

ENDERECO = {
    "street": "Rua Ali",
    "number": "120",
    "complement": None,
    "neighborhood": "Centro",
    "city": "Porto Alegre",
    "state": "rs",
    "zip_code": "90010000",
}


def _loja(**extra) -> dict:
    corpo = {
        "name": "Brechó Aurora",
        "document_type": "CPF",
        "document_value": "52998224725",
    }
    corpo.update(extra)
    return corpo


def _registrar(client: TestClient, email: str) -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={"name": "Vendedora", "email": email, "password": "senha123"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_criar_loja_grava_a_chave_pix(client: TestClient) -> None:
    h = _registrar(client, "pix@vintex.com")

    r = client.post(
        "/api/users/me/store", json=_loja(pix_key="aurora@vintex.com"), headers=h
    )

    assert r.status_code == 201, r.text
    assert r.json()["pix_key"] == "aurora@vintex.com"
    # E sobrevive a releitura: o valor foi para o banco, nao so para a resposta.
    assert (
        client.get("/api/users/me/store", headers=h).json()["pix_key"]
        == "aurora@vintex.com"
    )


def test_criar_loja_grava_o_endereco_e_o_publico_passa_a_devolver(
    client: TestClient,
) -> None:
    h = _registrar(client, "endereco@vintex.com")

    r = client.post("/api/users/me/store", json=_loja(address=ENDERECO), headers=h)
    assert r.status_code == 201, r.text
    loja_id = r.json()["id"]

    publico = client.get(f"/api/stores/{loja_id}")
    assert publico.status_code == 200, publico.text
    endereco = publico.json()["address"]

    assert endereco is not None, "o retrato publico devolvia address: null sempre"
    assert endereco["city"] == "Porto Alegre"
    assert endereco["neighborhood"] == "Centro"
    assert endereco["zip_code"] == "90010000"
    # UF normalizada: a tela manda o que o usuario digitou.
    assert endereco["state"] == "RS"


def test_loja_sem_descricao_sem_pix_e_sem_versao_de_contrato_e_valida(
    client: TestClient,
) -> None:
    """Modelagem secao 1.4: so `seller_id` e `name` sao obrigatorios."""
    h = _registrar(client, "minima@vintex.com")

    r = client.post("/api/users/me/store", json=_loja(), headers=h)

    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["description"] is None
    assert corpo["pix_key"] is None
    assert corpo["terms_version"] is None
    assert corpo["address"] is None


def test_descricao_vazia_deixou_de_ser_422(client: TestClient) -> None:
    h = _registrar(client, "vazia@vintex.com")

    r = client.post("/api/users/me/store", json=_loja(description=""), headers=h)

    assert r.status_code == 201, r.text


def test_versao_do_contrato_quando_vem_continua_sendo_gravada(
    client: TestClient,
) -> None:
    """Opcional nao quer dizer descartada: quando a `front-end#215` existir e
    mandar a versao, ela tem que ficar registrada com a data do aceite."""
    h = _registrar(client, "contrato@vintex.com")

    r = client.post("/api/users/me/store", json=_loja(terms_version="v0"), headers=h)

    assert r.status_code == 201, r.text
    assert r.json()["terms_version"] == "v0"
    assert r.json()["terms_accepted_at"] is not None


def test_uf_com_mais_de_duas_letras_e_recusada(client: TestClient) -> None:
    h = _registrar(client, "uf@vintex.com")
    endereco = {**ENDERECO, "state": "Rio Grande do Sul"}

    r = client.post("/api/users/me/store", json=_loja(address=endereco), headers=h)

    assert r.status_code == 422, r.text
    # Afere o campo, nao so o codigo: sem isto o teste passava tambem no codigo
    # antigo, onde o 422 vinha de `description` e `terms_version` faltando.
    assert "state" in str(r.json()["error"]["fields"]), r.text


def test_endereco_sem_rua_e_recusado_e_nao_cria_loja(client: TestClient) -> None:
    """Endereco parcial nao entra: linha em `addresses` com rua vazia seria
    pior que nao ter endereco."""
    h = _registrar(client, "parcial@vintex.com")
    endereco = {k: v for k, v in ENDERECO.items() if k != "street"}

    r = client.post("/api/users/me/store", json=_loja(address=endereco), headers=h)

    assert r.status_code == 422, r.text
    assert "street" in str(r.json()["error"]["fields"]), r.text
    assert client.get("/api/users/me/store", headers=h).status_code == 404


def test_chave_pix_nao_aparece_no_retrato_publico(client: TestClient) -> None:
    """A chave e dado do vendedor, nao da vitrine."""
    h = _registrar(client, "privado@vintex.com")
    r = client.post(
        "/api/users/me/store", json=_loja(pix_key="aurora@vintex.com"), headers=h
    )
    loja_id = r.json()["id"]

    publico = client.get(f"/api/stores/{loja_id}").json()

    assert "pix_key" not in publico
