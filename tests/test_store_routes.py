"""GET /api/stores/{id} e GET /api/stores/{id}/products (BE-US007-2, back-end#142)."""

from decimal import Decimal

from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_store(db_session, name: str = "Brechó Aurora", verified: bool = True) -> Store:
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
    address = Address(
        street="Rua Sete de Setembro",
        number="1020",
        neighborhood="Centro Histórico",
        city="Porto Alegre",
        state="RS",
        zip_code="90010-190",
    )
    store = Store(
        name=name, description="Peças de segunda mão.", seller=seller, address=address
    )
    db_session.add(store)
    db_session.commit()
    return store


def test_get_store_sem_login_devolve_dados_e_selo(client, db_session):
    store = make_store(db_session, verified=True)

    response = client.get(f"/api/stores/{store.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == store.id
    assert body["verified"] is True
    assert body["address"]["city"] == "Porto Alegre"
    assert body["metrics"] == {
        "created_at": body["metrics"]["created_at"],
        "products_listed": 0,
        "products_sold": 0,
    }


def test_get_store_404_quando_loja_nao_existe(client):
    response = client.get("/api/stores/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_list_store_products_so_traz_ativas_daquela_loja(client, db_session):
    store = make_store(db_session, name="Brechó A")
    outra_loja = make_store(db_session, name="Brechó B")
    ativo = Product(
        store=store,
        name="Jaqueta vintage",
        price=Decimal("99.90"),
        status="ativo",
        images=[ProductImage(image_url="https://cdn.test/cover.jpg", position=0)],
    )
    vendido = Product(
        store=store, name="Vendida", price=Decimal("50.00"), status="vendido"
    )
    de_outra_loja = Product(
        store=outra_loja,
        name="Peça de outro brechó",
        price=Decimal("10.00"),
        status="ativo",
    )
    db_session.add_all([ativo, vendido, de_outra_loja])
    db_session.commit()

    response = client.get(f"/api/stores/{store.id}/products")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"] == [
        {
            "id": ativo.id,
            "name": "Jaqueta vintage",
            "price": "99.90",
            "cover_image_url": "https://cdn.test/cover.jpg",
            "status": "ativo",
        }
    ]


def test_list_store_products_404_quando_loja_nao_existe(client):
    response = client.get("/api/stores/999999/products")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_list_store_products_pagina(client, db_session):
    store = make_store(db_session)
    for i in range(3):
        db_session.add(
            Product(
                store=store, name=f"Peça {i}", price=Decimal("10.00"), status="ativo"
            )
        )
    db_session.commit()

    response = client.get(f"/api/stores/{store.id}/products?page=1&page_size=2")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
