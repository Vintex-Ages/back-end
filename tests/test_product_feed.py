from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_store(db_session, name: str) -> Store:
    user = User(
        name=f"{name} owner",
        email=f"{name.lower().replace(' ', '.')}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(name)))[:11].zfill(11),
    )
    store = Store(name=name, seller=seller)
    db_session.add(store)
    db_session.flush()
    return store


def make_product(
    db_session,
    store: Store,
    name: str,
    created_at: datetime,
    status: str = "ativo",
    images: list[ProductImage] | None = None,
    **attributes,
) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal("99.90"),
        status=status,
        created_at=created_at,
        images=images or [],
        **attributes,
    )
    db_session.add(product)
    return product


def test_feed_returns_active_products_with_first_cover_and_store(client, db_session):
    store = make_store(db_session, "Brechó Aurora")
    product = make_product(
        db_session,
        store,
        "Jaqueta vintage",
        datetime.now(timezone.utc),
        images=[
            ProductImage(image_url="https://cdn.test/second.jpg", position=2),
            ProductImage(image_url="https://cdn.test/cover.jpg", position=1),
        ],
    )
    make_product(
        db_session,
        store,
        "Peça vendida",
        datetime.now(timezone.utc),
        status="vendido",
    )
    db_session.commit()

    response = client.get("/api/products")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0] == {
        "id": product.id,
        "name": "Jaqueta vintage",
        "price": "99.90",
        "cover_image_url": "https://cdn.test/cover.jpg",
        "store": {"id": store.id, "name": "Brechó Aurora"},
        "status": "ativo",
    }


def test_feed_returns_null_cover_and_paginates_by_recent(client, db_session):
    store = make_store(db_session, "Brechó Central")
    now = datetime.now(timezone.utc)
    make_product(db_session, store, "Mais novo", now)
    make_product(db_session, store, "Mais antigo", now - timedelta(days=1))
    db_session.commit()

    response = client.get("/api/products?page=2&page_size=1")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["total"] == 2
    assert body["items"][0]["name"] == "Mais antigo"
    assert body["items"][0]["cover_image_url"] is None


def test_feed_rejects_unknown_sort(client):
    response = client.get("/api/products?sort=oldest")

    assert response.status_code == 422


def test_feed_filters_each_product_attribute(client, db_session):
    store = make_store(db_session, "Brechó Filtros")
    now = datetime.now(timezone.utc)
    make_product(
        db_session,
        store,
        "Jaqueta azul",
        now,
        category="Jaquetas",
        size="M",
        brand="Marca A",
        condition="Bom",
        color="Azul",
        price=Decimal("120.00"),
    )
    make_product(
        db_session,
        store,
        "Vestido vermelho",
        now - timedelta(minutes=1),
        category="Vestidos",
        size="G",
        brand="Marca B",
        condition="Novo",
        color="Vermelho",
        price=Decimal("220.00"),
    )
    db_session.commit()

    for query in (
        "category=Jaquetas",
        "size=M",
        "brand=Marca+A",
        "condition=Bom",
        "color=Azul",
        "price_min=100&price_max=150",
    ):
        response = client.get(f"/api/products?{query}")
        assert response.status_code == 200
        assert response.json()["total"] == 1


def test_feed_combines_filters_with_and_and_reports_applied_filters(client, db_session):
    store = make_store(db_session, "Brechó Combinado")
    now = datetime.now(timezone.utc)
    matching = make_product(
        db_session,
        store,
        "Jaqueta azul",
        now,
        category="Jaquetas",
        size="M",
        brand="Marca A",
        condition="Bom",
        color="Azul",
        price=Decimal("120.00"),
    )
    make_product(
        db_session,
        store,
        "Jaqueta azul cara",
        now - timedelta(minutes=1),
        category="Jaquetas",
        size="M",
        brand="Marca A",
        condition="Bom",
        color="Azul",
        price=Decimal("220.00"),
    )
    db_session.commit()

    response = client.get(
        "/api/products?category=Jaquetas&size=M&brand=Marca+A"
        "&condition=Bom&color=Azul&price_min=100&price_max=150"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == matching.id
    assert body["applied_filters"] == {
        "category": "Jaquetas",
        "price_min": "100",
        "price_max": "150",
        "size": "M",
        "brand": "Marca A",
        "condition": "Bom",
        "color": "Azul",
    }


def test_feed_rejects_inverted_price_range(client):
    response = client.get("/api/products?price_min=200&price_max=100")

    assert response.status_code == 422
