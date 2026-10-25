from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference


class UserPreferenceRepository:
    """Persistência das preferências do usuário (issue #80).

    Toda operação recebe `user_id`: não existe leitura nem escrita de
    preferência sem dono.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: int) -> list[UserPreference]:
        # Ordem de gravação, para o GET devolver na ordem em que o PUT mandou.
        stmt = (
            select(UserPreference)
            .where(UserPreference.user_id == user_id)
            .order_by(UserPreference.id)
        )
        return list(self.db.scalars(stmt))

    def replace_for_user(
        self, user_id: int, items: list[tuple[str, str]]
    ) -> list[UserPreference]:
        # DELETE em lote executa na hora. Com `db.delete()` por objeto, o
        # flush do SQLAlchemy faz os INSERTs antes dos DELETEs, e regravar a
        # mesma preferência violaria a unique (user_id, type, value).
        self.db.execute(delete(UserPreference).where(UserPreference.user_id == user_id))
        preferences = [
            UserPreference(user_id=user_id, type=type_, value=value)
            for type_, value in items
        ]
        self.db.add_all(preferences)
        self.db.flush()
        return preferences
