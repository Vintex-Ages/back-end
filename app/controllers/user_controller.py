from sqlalchemy.orm import Session

from app.models.seller import Seller
from app.models.user import User
from app.schemas.user_schema import MeResponse


class UserController:
    def __init__(self, db: Session):
        self.db = db

    def get_me(self, user: User) -> MeResponse:
        # is_seller é derivado, não uma coluna: existe vendedor associado?
        # Um usuário pode ser comprador e vendedor ao mesmo tempo (ADR 0002).
        is_seller = (
            self.db.query(Seller).filter(Seller.user_id == user.id).first() is not None
        )
        return MeResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            is_admin=user.is_admin,
            is_seller=is_seller,
        )
