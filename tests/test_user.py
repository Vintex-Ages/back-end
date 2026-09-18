import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User


def persist_user(db_session, **overrides):
    data = {
        "name": "Usuário Teste",
        "email": "usuario@example.com",
        "password_hash": "hashed-password",
    }
    data.update(overrides)
    user = User(**data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_user_can_be_persisted_with_required_fields(db_session):
    user = persist_user(db_session)

    assert user.id is not None
    assert user.name == "Usuário Teste"
    assert user.email == "usuario@example.com"
    assert user.cpf is None
    assert user.phone is None
    assert user.address_id is None
    assert user.is_admin is False


def test_email_must_be_unique(db_session):
    persist_user(db_session, email="duplicado@example.com")

    with pytest.raises(IntegrityError):
        persist_user(db_session, email="duplicado@example.com")

    db_session.rollback()


def test_allows_multiple_users_without_cpf(db_session):
    first = persist_user(db_session, email="sem-cpf-1@example.com")
    second = persist_user(db_session, email="sem-cpf-2@example.com")

    assert first.cpf is None
    assert second.cpf is None


def test_cpf_must_be_unique_when_present(db_session):
    persist_user(db_session, email="cpf-1@example.com", cpf="123.456.789-00")

    with pytest.raises(IntegrityError):
        persist_user(db_session, email="cpf-2@example.com", cpf="123.456.789-00")

    db_session.rollback()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
