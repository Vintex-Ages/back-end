from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Favorite(Base):
    """Peça favoritada por um usuário (back-end#252).

    Não herda `BaseModel`: a chave é composta de `(user_id, product_id)`, sem
    `id` próprio. É ela que torna favoritar idempotente sem consulta prévia —
    o `INSERT ... ON CONFLICT DO NOTHING` do repository não tem como duplicar.
    `created_at` ordena a lista, mais recente primeiro.
    """

    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
