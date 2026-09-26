from sqlalchemy.orm import Session

from app.models.seller import Seller
from app.models.store import Store


class StoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: int) -> Store | None:
        return (
            self.db.query(Store)
            .join(Seller, Store.seller_id == Seller.id)
            .filter(Seller.user_id == user_id)
            .first()
        )

    def get_seller_by_user_id(self, user_id: int) -> Seller | None:
        return self.db.query(Seller).filter(Seller.user_id == user_id).first()

    def save(self, store: Store) -> Store:
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)
        return store
