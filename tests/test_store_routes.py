from app.models.seller import Seller
from app.models.store import Store
from tests.test_user import persist_user


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

    me_response = client.get("/api/users/me", headers={"X-User-Id": str(user.id)})
    assert me_response.status_code == 200
    assert me_response.json()["is_seller"] is True


def test_create_store_accepts_cnpj(client, db_session):
    user = persist_user(db_session, email="cnpj-owner@example.com")

    response = client.post(
        "/api/users/me/store",
        headers={"X-User-Id": str(user.id)},
        json=store_payload("CNPJ"),
    )

    assert response.status_code == 201
    assert response.json()["document_type"] == "CNPJ"


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

    me_response = client.get("/api/users/me", headers={"X-User-Id": str(user.id)})
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
