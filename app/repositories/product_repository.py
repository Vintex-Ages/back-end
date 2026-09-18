from decimal import Decimal
from typing import TypedDict, cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.store import Store
from app.schemas.product_schema import ProductFilters


class ProductFeedRow(TypedDict):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    store_id: int
    store_name: str


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_feed(
        self, params: PageParams, filters: ProductFilters
    ) -> tuple[list[ProductFeedRow], int]:
        cover_image_url = (
            select(ProductImage.image_url)
            .where(ProductImage.product_id == Product.id)
            .order_by(ProductImage.position.asc(), ProductImage.id.asc())
            .limit(1)
            .scalar_subquery()
        )
        conditions = [Product.status == "ativo"]
        filter_columns = {
            "category": Product.category,
            "size": Product.size,
            "brand": Product.brand,
            "condition": Product.condition,
            "color": Product.color,
        }
        for field_name, column in filter_columns.items():
            value = getattr(filters, field_name)
            if value is not None:
                conditions.append(column == value)
        if filters.price_min is not None:
            conditions.append(Product.price >= filters.price_min)
        if filters.price_max is not None:
            conditions.append(Product.price <= filters.price_max)

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
            .where(*conditions)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(ProductFeedRow, dict(row)) for row in rows], total
