from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_status_history import OrderStatusHistory


class OrderRepository:
    """Persistência do pedido (back-end#247 e back-end#280)."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, order: Order) -> Order:
        """Grava o pedido com os itens e o histórico que já estiverem nele.

        O `refresh` traz `created_at` e `changed_at`, que o banco preenche.
        """
        self.db.add(order)
        self.db.flush()
        self.db.refresh(order)
        for entry in order.status_history:
            self.db.refresh(entry)
        return order

    def expire_overdue(self, now: datetime) -> list[int]:
        """`aguardando_comprovante` vencido vira `expirado`, com linha no
        histórico, e devolve os ids que mudaram.

        Conferir e trocar no mesmo UPDATE, como no `reserve` das peças: se o
        comprovante chegar (`em_analise`) entre uma leitura e a gravação, o
        pedido já não casa com o WHERE e não é expirado por engano.
        """
        expired_ids = list(
            self.db.scalars(
                update(Order)
                .where(
                    Order.status == "aguardando_comprovante",
                    Order.expires_at < now,
                )
                .values(status="expirado")
                .returning(Order.id)
            )
        )
        self.db.add_all(
            OrderStatusHistory(order_id=order_id, status="expirado")
            for order_id in expired_ids
        )
        self.db.flush()
        return expired_ids

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
