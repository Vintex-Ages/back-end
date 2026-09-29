"""Rotas da loja: as publicas (back-end#142) e as do proprio vendedor
(back-end#141). Os dois conjuntos nasceram em PRs separados e foram unidos no
merge; nao ha sobreposicao de nomes entre eles."""

from decimal import Decimal

from app.core.security import create_access_token
from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from tests.test_user import persist_user


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
            # Numero, nao string, desde a `#212`.
            "price": 99.9,
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


def _auth_header(user) -> dict[str, str]:
    token = create_access_token(user.id, user.is_admin)
    return {"Authorization": f"Bearer {token}"}


def store_payload(document_type: str = "CPF") -> dict[str, str]:
    return {
        "name": "Brechó do Teste",
        "description": "Peças selecionadas",
        "logo_url": "https://example.com/logo.png",
        "document_type": document_type,
        "document_value": (
            "123.456.789-00" if document_type == "CPF" else "12.345.678/0001-90"
        ),
        "terms_version": "v1.0",
    }


def test_create_store_turns_user_into_seller_and_persists_terms(client, db_session):
    user = persist_user(db_session, email="store-owner@example.com")

    response = client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(user.id)},
        json=store_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Brechó do Teste"
    assert body["document_type"] == "CPF"
    assert body["terms_version"] == "v1.0"
    assert body["terms_accepted_at"] is not None
    assert db_session.query(Seller).filter_by(user_id=user.id).count() == 1
    assert db_session.query(Store).filter_by(seller_id=body["seller_id"]).count() == 1

    me_response = client.get("/api/users/me", headers=_auth_header(user))
    assert me_response.status_code == 200
    assert me_response.json()["is_seller"] is True


def test_create_store_sem_logo_e_aceito(client, db_session):
    """Brecho sem logo ainda e brecho: `Store.logo_url` e anulavel no modelo, e
    nao existe tela de upload de logo para exigir uma."""
    user = persist_user(db_session, email="sem-logo@example.com")
    corpo = store_payload()
    del corpo["logo_url"]

    response = client.post(
        "/api/users/me/store", headers={"X-User-Id": str(user.id)}, json=corpo
    )

    assert response.status_code == 201
    assert response.json()["logo_url"] is None


def test_create_store_accepts_cnpj(client, db_session):
    user = persist_user(db_session, email="cnpj-owner@example.com")

    response = client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(user.id)},
        json=store_payload("CNPJ"),
    )

    assert response.status_code == 201
    assert response.json()["document_type"] == "CNPJ"


def test_create_store_rejects_cpf_with_wrong_digit_count(client, db_session):
    user = persist_user(db_session, email="bad-cpf@example.com")

    response = client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(user.id)},
        json={**store_payload(), "document_value": "123.456.789-0"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_store_rejects_document_registered_by_another_seller(client, db_session):
    owner = persist_user(db_session, email="doc-owner@example.com")
    client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(owner.id)},
        json=store_payload(),
    )

    other_user = persist_user(db_session, email="doc-thief@example.com")
    response = client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(other_user.id)},
        json={**store_payload(), "name": "Outra loja"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_ALREADY_REGISTERED"
    assert db_session.query(Store).count() == 1


def test_second_store_creation_returns_conflict_without_creating_store(
    client, db_session
):
    user = persist_user(db_session, email="duplicate-store@example.com")
    headers = {"X-User-Id": str(user.id)}
    first_response = client.post(
        "/api/users/me/store", headers=headers, json=store_payload()
    )

    second_response = client.post(
        "/api/users/me/store",
        headers=headers,
        json={**store_payload(), "name": "Outra loja"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "STORE_ALREADY_EXISTS"
    assert db_session.query(Store).count() == 1
    assert db_session.query(Seller).count() == 1


def test_get_own_store_returns_not_found_for_user_without_store(client, db_session):
    user = persist_user(db_session, email="buyer@example.com")

    response = client.get("/api/users/me/store", headers={"X-User-Id": str(user.id)})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"

    me_response = client.get("/api/users/me", headers=_auth_header(user))
    assert me_response.status_code == 200
    assert me_response.json()["is_seller"] is False


def test_get_own_store_returns_created_store(client, db_session):
    user = persist_user(db_session, email="read-store@example.com")
    headers = {"X-User-Id": str(user.id)}
    client.post("/api/users/me/store", headers=headers, json=store_payload())

    response = client.get("/api/users/me/store", headers=headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Brechó do Teste"
    assert response.json()["logo_url"] == "https://example.com/logo.png"
