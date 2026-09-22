from decimal import Decimal

from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_seller_store(
    db_session, name: str, city: str = "Porto Alegre"
) -> tuple[User, Store]:
    slug = name.lower().replace(" ", ".")
    user = User(name=f"{name} owner", email=f"{slug}@test.local", password_hash="x")
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(name)))[:11].zfill(11),
    )
    store = Store(
        name=name,
        seller=seller,
        address=Address(
            street="Rua X", number="1", city=city, state="RS", zip_code="90000000"
        ),
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(store)
    return user, store


def test_create_draft_uses_store_from_current_user(client, db_session):
    user, store = make_seller_store(db_session, "Brecho Aurora", city="Porto Alegre")

    resp = client.post(
        "/api/users/me/products",
        json={"name": "Jaqueta jeans", "price": "149.90"},
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "rascunho"
    assert body["quantity"] == 1
    assert body["store"] == {"id": store.id, "name": store.name, "city": "Porto Alegre"}
    assert body["images"] == []
    assert body["ai_corrections"] == []


def test_create_draft_without_store_is_rejected(client, db_session):
    resp = client.post(
        "/api/users/me/products",
        json={"name": "Jaqueta", "price": "10.00"},
        headers={"X-User-Id": "999"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_update_draft_applies_only_sent_fields_and_accumulates_ai_corrections(
    client, db_session
):
    user, _ = make_seller_store(db_session, "Brecho Central")
    created = client.post(
        "/api/users/me/products",
        json={
            "name": "Vestido",
            "description": "Descrição original",
            "price": "80.00",
        },
        headers={"X-User-Id": str(user.id)},
    ).json()

    resp = client.patch(
        f"/api/products/{created['id']}",
        json={
            "price": "70.00",
            "images": ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"],
            "ai_corrections": [
                {"field": "category", "suggested": "Vestidos", "final": "Vestido longo"}
            ],
        },
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == "70.00"
    assert body["description"] == "Descrição original"
    assert body["images"] == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"]
    assert body["ai_corrections"] == [
        {"field": "category", "suggested": "Vestidos", "final": "Vestido longo"}
    ]

    resp2 = client.patch(
        f"/api/products/{created['id']}",
        json={
            "ai_corrections": [
                {"field": "color", "suggested": "Azul", "final": "Verde"}
            ]
        },
        headers={"X-User-Id": str(user.id)},
    )

    assert resp2.status_code == 200
    corrections = resp2.json()["ai_corrections"]
    assert len(corrections) == 2
    assert {"field": "color", "suggested": "Azul", "final": "Verde"} in corrections


def test_update_draft_rejects_other_sellers_product(client, db_session):
    owner, _ = make_seller_store(db_session, "Brecho Dono")
    intruder, _ = make_seller_store(db_session, "Brecho Intruso")
    created = client.post(
        "/api/users/me/products",
        json={"name": "Bolsa", "price": "50.00"},
        headers={"X-User-Id": str(owner.id)},
    ).json()

    resp = client.patch(
        f"/api/products/{created['id']}",
        json={"name": "Bolsa roubada"},
        headers={"X-User-Id": str(intruder.id)},
    )

    assert resp.status_code == 403


def test_update_draft_rejects_already_published_product(client, db_session):
    user, store = make_seller_store(db_session, "Brecho Publicado")
    product = Product(
        store=store,
        name="Camisa",
        price=Decimal("30.00"),
        status="ativo",
        images=[ProductImage(image_url="https://cdn.test/x.jpg", position=0)],
    )
    db_session.add(product)
    db_session.commit()

    resp = client.patch(
        f"/api/products/{product.id}",
        json={"name": "Camisa nova"},
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 409


def test_update_draft_missing_product_returns_404(client, db_session):
    user, _ = make_seller_store(db_session, "Brecho Vazio")

    resp = client.patch(
        "/api/products/999999",
        json={"name": "x"},
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_publish_requires_at_least_one_photo(client, db_session):
    user, _ = make_seller_store(db_session, "Brecho Sem Foto")
    created = client.post(
        "/api/users/me/products",
        json={"name": "Sapato", "price": "120.00"},
        headers={"X-User-Id": str(user.id)},
    ).json()

    resp = client.post(
        f"/api/users/me/products/{created['id']}/publish",
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "images" in body["error"]["fields"]


def test_publish_moves_draft_to_catalog_and_appears_in_feed(client, db_session):
    user, _ = make_seller_store(db_session, "Brecho Publica")
    created = client.post(
        "/api/users/me/products",
        json={
            "name": "Calça",
            "price": "90.00",
            "images": ["https://cdn.test/calca.jpg"],
        },
        headers={"X-User-Id": str(user.id)},
    ).json()

    resp = client.post(
        f"/api/users/me/products/{created['id']}/publish",
        headers={"X-User-Id": str(user.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ativo"

    feed = client.get("/api/products")
    assert any(item["id"] == created["id"] for item in feed.json()["items"])
