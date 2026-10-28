from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class StoreRating(BaseModel):
    """Nota de 1 a 5 que o comprador dá à loja de um pedido entregue
    (back-end#267).

    Só estrelas, sem comentário (RN-75): a tabela não tem coluna de texto de
    propósito. Só quem comprou avalia (RN-76), e uma vez por pedido: o
    `UNIQUE` em `order_id` é o que garante isso, inclusive em dois cliques ao
    mesmo tempo. O CHECK da nota está no banco, e não só no schema.

    `store_id` repete a loja do pedido para a média do perfil sair de uma
    consulta só nesta tabela, sem juntar com `orders`.
    """

    __tablename__ = "store_ratings"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_store_ratings_score"),
        Index("uq_store_ratings_order_id", "order_id", unique=True),
        Index("ix_store_ratings_store_id", "store_id"),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
