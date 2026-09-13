from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.product_image import ProductImage
    from app.models.store import Store


class Product(BaseModel):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("quantity = 1", name="ck_products_quantity"),
        CheckConstraint(
            "status IN ('ativo', 'vendido', 'despublicado')",
            name="ck_products_status",
        ),
        Index("ix_products_status", "status"),
        Index("ix_products_category", "category"),
        Index("ix_products_brand", "brand"),
        Index("ix_products_size", "size"),
        Index("ix_products_color", "color"),
        Index("ix_products_price", "price"),
    )

    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    style: Mapped[str | None] = mapped_column(String(80))
    brand: Mapped[str | None] = mapped_column(String(80))
    color: Mapped[str | None] = mapped_column(String(50))
    size: Mapped[str | None] = mapped_column(String(30))
    condition: Mapped[str | None] = mapped_column(String(50))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ativo", server_default="ativo"
    )

    store: Mapped["Store"] = relationship(back_populates="products")
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        order_by="ProductImage.position",
        cascade="all, delete-orphan",
    )
