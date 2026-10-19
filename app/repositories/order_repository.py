from sqlalchemy.orm import Session

from app.models.order import Order


class OrderRepository:
    """Persistência do pedido (back-end#247)."""

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

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
