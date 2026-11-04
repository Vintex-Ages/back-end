from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.product import Product


class OrderItem(BaseModel):
    """Peça de um pedido, congelada no momento da compra (back-end#243).

    Peça é única (RN-46): não há `quantity`, e a unique `(order_id,
    product_id)` impede a mesma peça duas vezes no pedido. A peça pode
    aparecer em outro pedido depois que este expirar, por isso `product_id`
    não é único sozinho.

    `store_id` só existe para a FK composta para `(orders.id,
    orders.store_id)`: um item não consegue apontar para pedido de outra loja.
    O banco não confere se `store_id` é a loja da peça; isso é regra do
    checkout.

    Nome, preço e capa são cópia: a peça pode ser editada ou sair do ar depois,
    e o pedido continua mostrando o que foi comprado.
    """

    __tablename__ = "order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "store_id"],
            ["orders.id", "orders.store_id"],
            name="fk_order_items_order_store",
        ),
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
        Index("ix_order_items_product_id", "product_id"),
    )

    order_id: Mapped[int] = mapped_column(nullable=False)
    store_id: Mapped[int] = mapped_column(nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(Text)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
