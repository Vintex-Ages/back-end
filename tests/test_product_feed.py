from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_store(
    db_session,
    name: str,
    verified: bool = False,
    *,
    city: str | None = None,
    state: str | None = None,
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
    address = None
    if city is not None and state is not None:
        address = Address(
            street="Rua de teste",
            number="1",
            city=city,
            state=state,
            zip_code="90000-000",
        )
    store = Store(name=name, seller=seller, address=address)
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
    price = attributes.pop("price", Decimal("99.90"))
    product = Product(
        store=store,
        name=name,
        price=price,
        status=status,
        created_at=created_at,
        images=images or [],
        **attributes,
    )
    db_session.add(product)
    return product


def test_feed_returns_active_products_with_first_cover_and_store(client, db_session):
    store = make_store(db_session, "Brechó Aurora", verified=True)
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
        "price": 99.90,
        "cover_image_url": "https://cdn.test/cover.jpg",
        "store": {"id": store.id, "name": "Brechó Aurora", "verified": True},
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
    # `price_min`/`price_max` saem como numero, nao string: eram os dois unicos
    # `Decimal` que escapavam do serializer, dentro deste dict (`#212`).
    assert body["applied_filters"] == {
        "category": "Jaquetas",
        "price_min": 100.0,
        "price_max": 150.0,
        "size": "M",
        "brand": "Marca A",
        "condition": "Bom",
        "color": "Azul",
    }


def test_feed_filters_by_store_city_and_state(client, db_session):
    porto_alegre = make_store(
        db_session, "Brechó Porto Alegre", city="Porto Alegre", state="RS"
    )
    sao_paulo = make_store(db_session, "Brechó São Paulo", city="São Paulo", state="SP")
    now = datetime.now(timezone.utc)
    porto_product = make_product(db_session, porto_alegre, "Peça RS", now)
    make_product(db_session, sao_paulo, "Peça SP", now - timedelta(minutes=1))
    db_session.commit()

    store_response = client.get(f"/api/products?store_id={porto_alegre.id}")
    city_response = client.get("/api/products?city=Porto+Alegre")
    state_response = client.get("/api/products?state=SP")

    for response in (store_response, city_response, state_response):
        assert response.status_code == 200
        assert response.json()["total"] == 1

    assert store_response.json()["items"][0]["id"] == porto_product.id
    assert store_response.json()["applied_filters"] == {"store_id": porto_alegre.id}
    assert city_response.json()["items"][0]["id"] == porto_product.id
    assert city_response.json()["applied_filters"] == {"city": "Porto Alegre"}
    assert state_response.json()["items"][0]["name"] == "Peça SP"
    assert state_response.json()["applied_filters"] == {"state": "SP"}


def test_feed_combines_store_location_and_product_filters(client, db_session):
    matching_store = make_store(
        db_session, "Brechó Curitiba", city="Curitiba", state="PR"
    )
    other_store = make_store(
        db_session, "Brechó Porto Alegre", city="Porto Alegre", state="RS"
    )
    now = datetime.now(timezone.utc)
    matching = make_product(
        db_session,
        matching_store,
        "Jaqueta PR",
        now,
        category="Jaquetas",
    )
    make_product(
        db_session,
        other_store,
        "Jaqueta RS",
        now - timedelta(minutes=1),
        category="Jaquetas",
    )
    db_session.commit()

    response = client.get(
        f"/api/products?store_id={matching_store.id}&city=Curitiba"
        "&state=PR&category=Jaquetas"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == matching.id
    assert body["applied_filters"] == {
        "category": "Jaquetas",
        "store_id": matching_store.id,
        "city": "Curitiba",
        "state": "PR",
    }


def test_feed_filter_without_matches_returns_catalog_suggestions(client, db_session):
    store = make_store(
        db_session, "Brechó Porto Alegre", city="Porto Alegre", state="RS"
    )
    product = make_product(
        db_session, store, "Peça disponível", datetime.now(timezone.utc)
    )
    db_session.commit()

    response = client.get("/api/products?city=Recife")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["match_type"] == "fallback"
    assert body["total"] == 1
    assert body["suggestions"]["items"][0]["id"] == product.id
    assert "filtros selecionados" in body["suggestions"]["reason"]
    assert body["applied_filters"] == {"city": "Recife"}


def test_feed_unknown_store_returns_404_without_authentication(client):
    response = client.get("/api/products?store_id=999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_feed_text_filters_ignore_case(client, db_session):
    store = make_store(db_session, "Brechó Normalizado")
    make_product(
        db_session,
        store,
        "Jaqueta azul",
        datetime.now(timezone.utc),
        category="Jaquetas",
        color="Azul",
    )
    db_session.commit()

    response = client.get("/api/products?category=jaquetas&color=azul")

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_feed_rejects_inverted_price_range(client):
    response = client.get("/api/products?price_min=200&price_max=100")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Dados inválidos na requisição."
    assert body["error"]["fields"]
