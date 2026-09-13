from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.product import Product
    from app.models.seller import Seller


class Store(BaseModel):
    __tablename__ = "stores"
    __table_args__ = (Index("ix_stores_name", "name"),)

    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id"), nullable=False)
    address_id: Mapped[int | None] = mapped_column(ForeignKey("addresses.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(Text)
    pix_key: Mapped[str | None] = mapped_column(String(255))

    seller: Mapped["Seller"] = relationship()
    address: Mapped["Address | None"] = relationship(back_populates="stores")
    products: Mapped[list["Product"]] = relationship(back_populates="store")
