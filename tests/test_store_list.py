"""Listagem pública dos brechós com busca por nome (back-end#256).

O formato é o que o front lê no `storeService.searchStores` (front-end#389):
`GET /api/stores?q=&page=`, num `Page` de `{items, page, page_size, total}`.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

STORES_URL = "/api/stores"


def make_store(
    session: Session,
    name: str,
    *,
    verified: bool = False,
    with_address: bool = True,
    description: str | None = "Peças de segunda mão.",
    logo_url: str | None = None,
) -> Store:
    user = User(
        name=f"{name} owner",
        email=f"{name.lower().replace(' ', '.')}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(name)))[:11].zfill(11),
        verified=verified,
    )
    address = (
        Address(
            street="Rua Sete de Setembro",
            number="1020",
            city="Porto Alegre",
            state="RS",
            zip_code="90010-190",
        )
        if with_address
        else None
    )
    store = Store(
        name=name,
        description=description,
        logo_url=logo_url,
        seller=seller,
        address=address,
    )
    session.add(store)
    session.flush()
    return store


def make_product(session: Session, store: Store, status: str = "ativo") -> Product:
    product = Product(
        store=store, name="Jaqueta", price=Decimal("99.90"), status=status
    )
    session.add(product)
    session.flush()
    return product


def names(response) -> list[str]:
    return [item["name"] for item in response.json()["items"]]


def test_lista_os_brechos_em_ordem_de_nome_e_sem_login(client, db_session):
    make_store(db_session, "Garimpo da Redenção")
    make_store(db_session, "Brechó Aurora")
    db_session.commit()

    response = client.get(STORES_URL)

    assert response.status_code == 200
    assert names(response) == ["Brechó Aurora", "Garimpo da Redenção"]
    assert response.json()["total"] == 2


def test_item_tem_o_formato_que_o_front_le(client, db_session):
    store = make_store(
        db_session,
        "Brechó Aurora",
        verified=True,
        logo_url="https://cdn.test/logo.png",
    )
    make_product(db_session, store)
    db_session.commit()

    response = client.get(STORES_URL)

    assert response.json() == {
        "items": [
            {
                "id": store.id,
                "name": "Brechó Aurora",
                "description": "Peças de segunda mão.",
                "logo_url": "https://cdn.test/logo.png",
                "verified": True,
                "city": "Porto Alegre",
                "state": "RS",
                "active_count": 1,
            }
        ],
        "page": 1,
        "page_size": 20,
        "total": 1,
    }


@pytest.mark.parametrize("q", ["reden", "REDEN", "da Re"])
def test_busca_por_parte_do_nome_sem_diferenciar_maiuscula(client, db_session, q):
    make_store(db_session, "Garimpo da Redenção")
    make_store(db_session, "Brechó Aurora")
    db_session.commit()

    response = client.get(STORES_URL, params={"q": q})

    assert names(response) == ["Garimpo da Redenção"]
    assert response.json()["total"] == 1


def test_busca_casa_so_o_nome_e_nao_a_cidade(client, db_session):
    make_store(db_session, "Brechó Aurora")
    db_session.commit()

    response = client.get(STORES_URL, params={"q": "Porto Alegre"})

    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_q_em_branco_lista_todos(client, db_session):
    make_store(db_session, "Brechó Aurora")
    make_store(db_session, "Brechó Brisa")
    db_session.commit()

    response = client.get(STORES_URL, params={"q": "   "})

    assert response.json()["total"] == 2


def test_active_count_conta_so_peca_ativo(client, db_session):
    """Uma peça em cada situação: só a `ativo` conta."""
    store = make_store(db_session, "Brechó Aurora")
    for status in ("rascunho", "ativo", "reservado", "vendido", "despublicado"):
        make_product(db_session, store, status=status)
    vazia = make_store(db_session, "Brechó Brisa")
    db_session.commit()

    items = {
        item["id"]: item["active_count"]
        for item in client.get(STORES_URL).json()["items"]
    }

    assert items == {store.id: 1, vazia.id: 0}


def test_perfil_da_loja_devolve_a_mesma_contagem(client, db_session):
    store = make_store(db_session, "Brechó Aurora")
    for status in ("ativo", "ativo", "vendido", "despublicado"):
        make_product(db_session, store, status=status)
    db_session.commit()

    na_lista = client.get(STORES_URL).json()["items"][0]["active_count"]
    metrics = client.get(f"{STORES_URL}/{store.id}").json()["metrics"]

    assert na_lista == 2
    assert metrics["active_count"] == 2
    assert metrics["products_listed"] == 2
    assert metrics["products_sold"] == 1


def test_loja_sem_endereco_vem_com_cidade_e_estado_nulos(client, db_session):
    make_store(db_session, "Brechó Sem Endereço", with_address=False, description=None)
    db_session.commit()

    response = client.get(STORES_URL)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert (item["city"], item["state"], item["description"]) == (None, None, None)


def test_lista_e_paginada(client, db_session):
    for name in ("Brechó A", "Brechó B", "Brechó C"):
        make_store(db_session, name)
    db_session.commit()

    body = client.get(STORES_URL, params={"page": 2, "page_size": 2}).json()

    assert (body["page"], body["page_size"], body["total"]) == (2, 2, 3)
    assert [item["name"] for item in body["items"]] == ["Brechó C"]


def test_q_maior_que_o_limite_responde_422(client, db_session):
    response = client.get(STORES_URL, params={"q": "x" * 101})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.postgres
def test_no_postgres_a_busca_ignora_acento(pg_client, pg_session):
    make_store(pg_session, "Garimpo da Redenção")
    make_store(pg_session, "Brechó Aurora")
    pg_session.commit()

    assert names(pg_client.get(STORES_URL, params={"q": "redencao"})) == [
        "Garimpo da Redenção"
    ]
    assert names(pg_client.get(STORES_URL, params={"q": "BRECHO"})) == ["Brechó Aurora"]
