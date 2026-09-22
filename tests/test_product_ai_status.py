"""GET /api/users/me/products/{id}/ai-status (VE-05, back-end#62)."""

from decimal import Decimal

from app.models.product import Product
from app.models.store import Store


def make_store(db_session, name: str = "Brechó Teste") -> Store:
    store = Store(seller_id=1, name=name)
    db_session.add(store)
    db_session.flush()
    return store


def test_status_not_requested_quando_ia_nunca_foi_solicitada(
    client, db_session
) -> None:
    store = make_store(db_session)
    product = Product(store=store, name="Jaqueta", price=Decimal("99.90"))
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/users/me/products/{product.id}/ai-status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "not_requested",
        "error": None,
        "suggestions": None,
    }


def test_status_done_retorna_sugestoes(client, db_session) -> None:
    store = make_store(db_session)
    product = Product(
        store=store,
        name="Jaqueta",
        price=Decimal("99.90"),
        ai_status="done",
        ai_suggestions={"category": {"value": "Jaqueta", "confidence": 0.9}},
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/users/me/products/{product.id}/ai-status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["suggestions"]["category"] == {"value": "Jaqueta", "confidence": 0.9}


def test_status_failed_retorna_erro(client, db_session) -> None:
    store = make_store(db_session)
    product = Product(
        store=store,
        name="Jaqueta",
        price=Decimal("99.90"),
        ai_status="failed",
        ai_error="Provedor de IA indisponível ou falhou na análise.",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/users/me/products/{product.id}/ai-status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "Provedor de IA indisponível ou falhou na análise."
    assert body["suggestions"] is None


def test_status_404_quando_peca_nao_existe(client) -> None:
    response = client.get("/api/users/me/products/999999/ai-status")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
