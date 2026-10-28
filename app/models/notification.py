from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel

# Os dois eventos da RN-85: a venda, ao vendedor, e o favorito, ao anunciante.
# Os nomes são os do modelo do front (`front-end/src/types/notification.ts`).
# A despublicação pela administradora (RN-80, VS-034) é um terceiro tipo, que
# entra aqui e no CHECK quando chegar: a coluna já é texto, não booleano.
NotificationType = Literal["sale", "favorite"]
NOTIFICATION_TYPES: tuple[str, ...] = get_args(NotificationType)
NOTIFICATION_TYPE_CHECK = "type IN ({})".format(
    ", ".join(f"'{tipo}'" for tipo in NOTIFICATION_TYPES)
)
# Condição do índice único parcial dos favoritos. É texto porque o mesmo
# predicado vai no índice, na migration e no `ON CONFLICT` do repository.
FAVORITE_WHERE = "type = 'favorite'"


class Notification(BaseModel):
    """Aviso dentro do produto para um usuário (back-end#261).

    Só in-app (RN-84): nada aqui é enviado por e-mail nem por push. A linha é
    o aviso; a tela lê, e marcar como lida preenche `read_at`.

    `product_id` é a peça de que o aviso fala: a favoritada, ou a primeira do
    pedido na venda. `order_id` só existe na venda. `actor_id` é quem
    favoritou: não sai na resposta, existe para o índice único impedir que
    favoritar, desfavoritar e favoritar de novo avise duas vezes.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(NOTIFICATION_TYPE_CHECK, name="ck_notifications_type"),
        CheckConstraint(
            "(type = 'sale' AND order_id IS NOT NULL)"
            " OR (type <> 'sale' AND order_id IS NULL)",
            name="ck_notifications_order",
        ),
        # A lista do usuário, mais recente primeiro.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index(
            "uq_notifications_favorite",
            "product_id",
            "actor_id",
            unique=True,
            postgresql_where=text(FAVORITE_WHERE),
            sqlite_where=text(FAVORITE_WHERE),
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
