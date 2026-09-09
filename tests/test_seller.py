from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.seller import Seller
from tests.test_user import persist_user


def persist_seller(db_session, **overrides):
    if "user_id" not in overrides:
        user = persist_user(
            db_session,
            email=overrides.pop("user_email", "seller-user@example.com"),
        )
        overrides["user_id"] = user.id

    data = {
        "document_type": "CPF",
        "document_value": "123.456.789-00",
    }
    data.update(overrides)
    seller = Seller(**data)
    db_session.add(seller)
    db_session.commit()
    db_session.refresh(seller)
    return seller


def test_seller_can_be_persisted_with_required_fields(db_session):
    seller = persist_seller(db_session)

    assert seller.id is not None
    assert seller.user_id is not None
    assert seller.document_type == "CPF"
    assert seller.document_value == "123.456.789-00"
    assert seller.verified is False
    assert seller.terms_version is None
    assert seller.terms_accepted_at is None


def test_user_id_must_be_unique(db_session):
    user = persist_user(db_session, email="seller-unique@example.com")
    persist_seller(
        db_session,
        user_id=user.id,
        document_value="123.456.789-00",
    )

    with pytest.raises(IntegrityError):
        persist_seller(
            db_session,
            user_id=user.id,
            document_value="987.654.321-00",
        )

    db_session.rollback()


def test_document_value_must_be_unique(db_session):
    persist_seller(
        db_session,
        user_email="seller-doc-1@example.com",
        document_value="123.456.789-00",
    )

    with pytest.raises(IntegrityError):
        persist_seller(
            db_session,
            user_email="seller-doc-2@example.com",
            document_value="123.456.789-00",
        )

    db_session.rollback()


def test_document_type_accepts_cpf_and_cnpj(db_session):
    cpf_seller = persist_seller(
        db_session,
        user_email="seller-cpf@example.com",
        document_type="CPF",
        document_value="123.456.789-00",
    )
    cnpj_seller = persist_seller(
        db_session,
        user_email="seller-cnpj@example.com",
        document_type="CNPJ",
        document_value="12.345.678/0001-90",
    )

    assert cpf_seller.document_type == "CPF"
    assert cnpj_seller.document_type == "CNPJ"


def test_document_type_rejects_other_values(db_session):
    with pytest.raises(IntegrityError):
        persist_seller(db_session, document_type="RG")

    db_session.rollback()


def test_seller_can_store_terms_metadata(db_session):
    accepted_at = datetime(2026, 9, 6, 12, 0, 0)

    seller = persist_seller(
        db_session,
        terms_version="v2026.09",
        terms_accepted_at=accepted_at,
    )

    assert seller.terms_version == "v2026.09"
    assert seller.terms_accepted_at == accepted_at
