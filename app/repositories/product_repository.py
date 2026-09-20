from decimal import Decimal
from typing import TypedDict, cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams, paginate
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store


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

    def get_active_feed(self, params: PageParams) -> tuple[list[ProductFeedRow], int]:
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
        return [cast(ProductFeedRow, dict(row)) for row in rows], total

    def list_for_seller(
        self, user_id: int, params: PageParams, status: str | None = None
    ) -> Page[Product]:
        stmt = (
            select(Product)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        if status is not None:
            stmt = stmt.where(Product.status == status)
        return cast(Page[Product], paginate(self.db, stmt, params))

    def get_for_seller(self, product_id: int, user_id: int) -> Product | None:
        return self.db.scalar(
            select(Product)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Product.id == product_id, Seller.user_id == user_id)
        )

    def save(self, product: Product) -> Product:
        self.db.commit()
        self.db.refresh(product)
        return product
