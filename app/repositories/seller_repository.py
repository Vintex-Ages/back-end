from sqlalchemy.orm import Session

from app.models.seller import Seller


class SellerRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists_for_user(self, user_id: int) -> bool:
        """Um usuário pode ser comprador e vendedor ao mesmo tempo (ADR 0002) —
        isto é uma consulta de existência, não uma coluna."""
        return (
            self.db.query(Seller).filter(Seller.user_id == user_id).first() is not None
        )
