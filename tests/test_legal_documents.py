from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.legal_document import SELLER_CONTRACT, TERMS_OF_USE, LegalDocument
from app.seeds.legal import seed_legal

TERMS_URL = "/api/legal/terms"
CONTRACT_URL = "/api/legal/seller-contract"


def persist_document(db_session, **overrides):
    data = {
        "document_type": TERMS_OF_USE,
        "version": "v0",
        "content": "Texto provisório.",
        "published_at": datetime(2026, 9, 1),
    }
    data.update(overrides)
    document = LegalDocument(**data)
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def test_terms_route_returns_document_without_login(client, db_session):
    persist_document(db_session, content="Termos v0.")

    resp = client.get(TERMS_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["document_type"] == TERMS_OF_USE
    assert body["version"] == "v0"
    assert body["content"] == "Termos v0."
    assert "published_at" in body


def test_seller_contract_route_returns_its_own_document(client, db_session):
    persist_document(db_session, content="Termos v0.")
    persist_document(db_session, document_type=SELLER_CONTRACT, content="Contrato.")

    resp = client.get(CONTRACT_URL)

    assert resp.status_code == 200
    body = resp.json()
    assert body["document_type"] == SELLER_CONTRACT
    assert body["content"] == "Contrato."


@pytest.mark.parametrize("url", [TERMS_URL, CONTRACT_URL])
def test_route_returns_404_envelope_when_document_is_missing(client, url):
    resp = client.get(url)

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "LEGAL_DOCUMENT_NOT_FOUND"


def test_new_version_replaces_current_and_keeps_the_old_one(client, db_session):
    persist_document(db_session, version="v0", content="Provisório.")
    persist_document(
        db_session,
        version="v1",
        content="Oficial.",
        published_at=datetime(2026, 9, 20),
    )

    body = client.get(TERMS_URL).json()

    assert body["version"] == "v1"
    assert body["content"] == "Oficial."
    versions = db_session.scalars(
        select(LegalDocument.version).where(LegalDocument.document_type == TERMS_OF_USE)
    ).all()
    assert sorted(versions) == ["v0", "v1"]


def test_same_type_and_version_cannot_be_inserted_twice(db_session):
    persist_document(db_session)

    with pytest.raises(IntegrityError):
        persist_document(db_session, content="Outro texto.")


def test_same_version_is_allowed_for_different_types(db_session):
    persist_document(db_session, document_type=TERMS_OF_USE)
    persist_document(db_session, document_type=SELLER_CONTRACT)

    assert db_session.query(LegalDocument).count() == 2


def test_seed_creates_v0_of_both_documents(client, db_session):
    assert seed_legal(db_session) == 2
    db_session.commit()

    for url in (TERMS_URL, CONTRACT_URL):
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.json()["version"] == "v0"


def test_seed_is_idempotent(db_session):
    seed_legal(db_session)
    db_session.commit()

    assert seed_legal(db_session) == 0
    assert db_session.query(LegalDocument).count() == 2
