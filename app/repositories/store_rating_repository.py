from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.store_rating import StoreRating


class StoreRatingSummary(TypedDict):
    average: float | None
    count: int


class StoreRatingRepository:
    """Persistência das avaliações da loja (back-end#267). Nada aqui faz
    commit."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, rating: StoreRating) -> StoreRating:
        """O `flush` é o que bate no `UNIQUE` de `order_id`: o segundo voto no
        mesmo pedido levanta `IntegrityError` aqui, e o controller traduz."""
        self.db.add(rating)
        self.db.flush()
        self.db.refresh(rating)
        return rating

    def summary_for_store(self, store_id: int) -> StoreRatingSummary:
        """Média e contagem numa consulta só. Sem avaliação, `AVG` é `NULL`, e
        a média volta `None`, nunca zero."""
        row = self.db.execute(
            select(
                func.avg(StoreRating.score).label("average"),
                func.count(StoreRating.id).label("total"),
            ).where(StoreRating.store_id == store_id)
        ).one()
        return StoreRatingSummary(
            average=float(row.average) if row.average is not None else None,
            count=int(row.total),
        )

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
