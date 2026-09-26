"""POST /api/users/me/store/verification (BE-US007-1, back-end#143)."""

from app.models.seller import Seller
from app.models.user import User


def make_seller(
    db_session,
    user_id: int,
    document_type: str = "CPF",
    document_value: str = "123.456.789-00",
    verified: bool = False,
) -> Seller:
    user = User(
        id=user_id,
        name="Dona da loja",
        email=f"dona-{user_id}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type=document_type,
        document_value=document_value,
        verified=verified,
    )
    db_session.add(seller)
    db_session.commit()
    return seller


def test_verification_muda_pendente_para_confiavel(client, db_session) -> None:
    make_seller(db_session, user_id=1)

    response = client.post(
        "/api/users/me/store/verification", headers={"X-User-Id": "1"}
    )

    assert response.status_code == 200
    assert response.json() == {"verified": True}


def test_verification_e_idempotente(client, db_session) -> None:
    make_seller(db_session, user_id=1, verified=True)

    response = client.post(
        "/api/users/me/store/verification", headers={"X-User-Id": "1"}
    )

    assert response.status_code == 200
    assert response.json() == {"verified": True}


def test_verification_404_quando_usuario_nao_e_vendedor(client) -> None:
    response = client.post(
        "/api/users/me/store/verification", headers={"X-User-Id": "1"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_verification_422_quando_documento_nao_bate_com_o_tipo(
    client, db_session
) -> None:
    make_seller(
        db_session,
        user_id=1,
        document_type="CNPJ",
        document_value="123.456.789-00",
    )

    response = client.post(
        "/api/users/me/store/verification", headers={"X-User-Id": "1"}
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "document_value" in body["error"]["fields"]
