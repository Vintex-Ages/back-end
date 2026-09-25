from decimal import Decimal

from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_store(db_session, user_id: int, name: str) -> Store:
    user = User(
        id=user_id,
        name=f"Owner {name}",
        email=f"{name.lower()}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(user_id).zfill(11),
    )
    store = Store(name=name, seller=seller)
    db_session.add(store)
    db_session.flush()
    return store


def make_product(db_session, store: Store, name: str, status: str) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal("99.90"),
        status=status,
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_seller_lists_all_statuses_and_filters(client, db_session):
    store = make_store(db_session, 10, "Aurora")
    make_product(db_session, store, "Ativa", "ativo")
    sold = make_product(db_session, store, "Vendida", "vendido")
    make_product(db_session, store, "Fora do ar", "despublicado")
    db_session.commit()

    response = client.get("/api/users/me/products", headers={"X-User-Id": "10"})

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert {item["id"] for item in response.json()["items"]} >= {sold.id}

    response = client.get(
        "/api/users/me/products?status=vendido", headers={"X-User-Id": "10"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["status"] == "vendido"


def test_seller_cannot_see_or_edit_another_sellers_product(client, db_session):
    own_store = make_store(db_session, 20, "Own")
    other_store = make_store(db_session, 21, "Other")
    other_product = make_product(db_session, other_store, "Other product", "ativo")
    make_product(db_session, own_store, "Own product", "ativo")
    db_session.commit()

    response = client.get("/api/users/me/products", headers={"X-User-Id": "20"})
    assert response.status_code == 200
    assert all(item["id"] != other_product.id for item in response.json()["items"])

    response = client.patch(
        f"/api/users/me/products/{other_product.id}",
        json={"name": "Tampered"},
        headers={"X-User-Id": "20"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_sold_product_cannot_be_edited(client, db_session):
    store = make_store(db_session, 30, "Sold")
    product = make_product(db_session, store, "Sold product", "vendido")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"name": "Changed"},
        headers={"X-User-Id": "30"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_SOLD"


def test_draft_product_can_be_edited_with_patch(client, db_session):
    store = make_store(db_session, 35, "Draft")
    product = make_product(db_session, store, "Draft product", "despublicado")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"name": "Edited draft"},
        headers={"X-User-Id": "35"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Edited draft"


def test_update_rejects_explicit_null_for_required_field(client, db_session):
    store = make_store(db_session, 36, "Null")
    product = make_product(db_session, store, "Null product", "ativo")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"price": None},
        headers={"X-User-Id": "36"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_product_can_be_unpublished(client, db_session):
    store = make_store(db_session, 40, "Cycle")
    product = make_product(db_session, store, "Cycle product", "ativo")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers={"X-User-Id": "40"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "despublicado"
    assert db_session.get(Product, product.id) is not None

    response = client.put(
        f"/api/users/me/products/{product.id}",
        json={"name": "No PUT"},
        headers={"X-User-Id": "40"},
    )
    assert response.status_code == 405

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers={"X-User-Id": "40"},
    )
    assert response.status_code == 404
