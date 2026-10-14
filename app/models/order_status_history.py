from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.order import ORDER_STATUS_CHECK

if TYPE_CHECKING:
    from app.models.order import Order


class OrderStatusHistory(BaseModel):
    """Uma linha por transição de status do pedido (back-end#243).

    A tela do pedido mostra a data de cada etapa atingida. `orders.status`
    com `updated_at` é sobrescrito a cada mudança e não reconstrói as datas
    anteriores, então cada transição grava uma linha aqui.

    Depois de `confirmado`, as etapas seguintes são derivadas na leitura a
    partir de `changed_at` da linha `confirmado`, e não geram linha.
    """

    __tablename__ = "order_status_history"
    __table_args__ = (
        CheckConstraint(ORDER_STATUS_CHECK, name="ck_order_status_history_status"),
        Index("ix_order_status_history_order_id", "order_id"),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    order: Mapped["Order"] = relationship(back_populates="status_history")
