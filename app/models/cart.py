from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class CartItem(BaseModel):
    """Peça no carrinho de um comprador (issue #147).

    Não tem `quantity` (peça é única) nem `store_id`: a loja vem de
    `Product.store_id` por join, para não guardar a mesma informação em dois
    lugares. A unique `(user_id, product_id)` garante que adicionar a mesma
    peça duas vezes não duplica a linha.
    """

    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_items_user_product"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped["User"] = relationship()
    product: Mapped["Product"] = relationship()
