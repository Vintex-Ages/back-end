from typing import TypedDict

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.pagination import PageParams
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

    def get_active_products(
        self, store_id: int, params: PageParams
    ) -> tuple[list[Product], int]:
        """Peças ativas daquela loja, paginadas — mais recentes primeiro.

        Pagina manualmente (contagem + offset/limit) em vez de `paginate()`
        genérico: os itens precisam de pós-processamento (`cover_image_url`
        a partir de `images`) que o helper não cobre.
        """
        stmt = (
            select(Product)
            .options(selectinload(Product.images))
            .where(Product.store_id == store_id, Product.status == "ativo")
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = self.db.scalars(stmt.offset(params.offset).limit(params.limit)).all()
        return list(rows), total
