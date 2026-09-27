from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.seller_repository import SellerRepository
from app.schemas.user_schema import MeResponse


class UserController:
    def __init__(self, db: Session):
        self.db = db
        self.sellers = SellerRepository(db)

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
