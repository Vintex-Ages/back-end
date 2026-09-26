from typing import TypedDict

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.product import Product
from app.models.store import Store


class StoreMetricsRow(TypedDict):
    products_listed: int
    products_sold: int


class StoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, store_id: int) -> Store | None:
        """Loja pública — já traz `seller` (pro selo) e `address` numa consulta só."""
        return self.db.scalar(
            select(Store)
            .options(joinedload(Store.seller), joinedload(Store.address))
            .where(Store.id == store_id)
        )

    def get_metrics(self, store_id: int) -> StoreMetricsRow:
        """Peças anunciadas (qualquer status) e vendidas, numa consulta agregada só."""
        row = self.db.execute(
            select(
                func.count(Product.id).label("products_listed"),
                func.coalesce(
                    func.sum(case((Product.status == "vendido", 1), else_=0)), 0
                ).label("products_sold"),
            ).where(Product.store_id == store_id)
        ).one()
        return StoreMetricsRow(
            products_listed=row.products_listed,
            products_sold=int(row.products_sold),
        )

    def active_products_query(self, store_id: int) -> Select[tuple[Product]]:
        """`Select` pronto para `paginate()` — peças ativas daquela loja, mais recentes primeiro."""
        return (
            select(Product)
            .options(selectinload(Product.images))
            .where(Product.store_id == store_id, Product.status == "ativo")
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
