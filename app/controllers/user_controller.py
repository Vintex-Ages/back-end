from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_preference import UserPreference
from app.repositories.seller_repository import SellerRepository
from app.repositories.user_preference_repository import UserPreferenceRepository
from app.schemas.user_schema import (
    MeResponse,
    PreferenceItem,
    PreferencesRequest,
    PreferencesResponse,
)


class UserController:
    def __init__(self, db: Session):
        self.db = db
        self.sellers = SellerRepository(db)
        self.preferences = UserPreferenceRepository(db)

    def get_me(self, user: User) -> MeResponse:
        # is_seller é derivado, não uma coluna: existe vendedor associado?
        # Um usuário pode ser comprador e vendedor ao mesmo tempo (ADR 0002).
        # A checagem mora em SellerRepository — mesma fonte usada por
        # require_seller (app/core/security.py), pra não divergir.
        return MeResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            is_admin=user.is_admin,
            is_seller=self.sellers.exists_for_user(user.id),
        )

    def get_preferences(self, user: User) -> PreferencesResponse:
        return self._to_response(self.preferences.list_for_user(user.id))

    def replace_preferences(
        self, user: User, payload: PreferencesRequest
    ) -> PreferencesResponse:
        """Substitui o conjunto inteiro (idempotente). Lista vazia limpa o
        perfil. Item repetido no corpo é gravado uma vez só: a unique
        (user_id, type, value) não aceitaria o segundo, e mandar duas vezes a
        mesma escolha não é erro de quem chama."""
        items = list(dict.fromkeys((p.type, p.value) for p in payload.preferences))
        try:
            saved = self.preferences.replace_for_user(user.id, items)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._to_response(saved)

    @staticmethod
    def _to_response(preferences: list[UserPreference]) -> PreferencesResponse:
        return PreferencesResponse(
            preferences=[PreferenceItem.model_validate(p) for p in preferences]
        )
