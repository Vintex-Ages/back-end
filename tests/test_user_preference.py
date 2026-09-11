import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user_preference import UserPreference
from tests.test_user import persist_user


def persist_preference(db_session, **overrides):
    if "user_id" not in overrides:
        user = persist_user(
            db_session,
            email=overrides.pop("user_email", "pref-user@example.com"),
        )
        overrides["user_id"] = user.id

    data = {"type": "estilo", "value": "streetwear"}
    data.update(overrides)
    preference = UserPreference(**data)
    db_session.add(preference)
    db_session.commit()
    db_session.refresh(preference)
    return preference


def test_preference_can_be_persisted_with_required_fields(db_session):
    preference = persist_preference(db_session)

    assert preference.id is not None
    assert preference.user_id is not None
    assert preference.type == "estilo"
    assert preference.value == "streetwear"


def test_user_can_have_many_preferences(db_session):
    user = persist_user(db_session, email="pref-many@example.com")

    persist_preference(db_session, user_id=user.id, value="streetwear")
    persist_preference(db_session, user_id=user.id, value="alfaiataria")

    total = (
        db_session.query(UserPreference)
        .filter(UserPreference.user_id == user.id)
        .count()
    )
    assert total == 2


def test_same_user_type_value_is_unique(db_session):
    user = persist_user(db_session, email="pref-unique@example.com")
    persist_preference(db_session, user_id=user.id, type="estilo", value="y2k")

    with pytest.raises(IntegrityError):
        persist_preference(db_session, user_id=user.id, type="estilo", value="y2k")

    db_session.rollback()
