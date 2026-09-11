from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.store import Store


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_feed(
        self, params: PageParams
    ) -> tuple[list[dict[str, object]], int]:
        cover_image_url = (
            select(ProductImage.image_url)
            .where(ProductImage.product_id == Product.id)
            .order_by(ProductImage.position.asc(), ProductImage.id.asc())
            .limit(1)
            .scalar_subquery()
        )
        stmt: Select[tuple[object, ...]] = (
            select(
                Product.id,
                Product.name,
                Product.price,
                cover_image_url.label("cover_image_url"),
                Product.status,
                Store.id.label("store_id"),
                Store.name.label("store_name"),
            )
            .join(Store, Store.id == Product.store_id)
            .where(Product.status == "ativo")
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total
