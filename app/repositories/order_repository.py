from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.pagination import PageParams
from app.models.order import Order
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment


class OrderRepository:
    """Persistência do pedido (back-end#247, #248, #251 e #280)."""

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

    def list_for_buyer(
        self, buyer_id: int, params: PageParams
    ) -> tuple[list[Order], int]:
        """Pedidos de quem compra, mais recente primeiro, e o total (back-end#248).

        Itens, pagamentos e histórico vêm em consultas próprias por coleção
        (`selectinload`), e não uma por pedido: a página inteira são cinco
        consultas, qualquer que seja o tamanho dela. O histórico entra mesmo
        sem sair na lista, porque é dele que o status derivado é calculado.
        """
        do_comprador = Order.buyer_id == buyer_id
        total = self.db.scalar(select(func.count(Order.id)).where(do_comprador)) or 0
        orders = self.db.scalars(
            select(Order)
            .where(do_comprador)
            .options(
                joinedload(Order.store),
                selectinload(Order.items),
                selectinload(Order.payments),
                selectinload(Order.status_history),
            )
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        ).all()
        return list(orders), total

    def get_for_buyer(self, order_id: int, buyer_id: int) -> Order | None:
        """O pedido, só se for de quem pede. De outra pessoa volta `None`, e a
        rota responde 404 como se não existisse: um 403 confirmaria o id."""
        return self.db.scalar(
            select(Order)
            .where(Order.id == order_id, Order.buyer_id == buyer_id)
            .options(
                joinedload(Order.store),
                selectinload(Order.items),
                selectinload(Order.payments),
                selectinload(Order.status_history),
            )
        )

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

    def get(self, order_id: int) -> Order | None:
        return self.db.get(Order, order_id)

    def transition(self, order_id: int, de: str, para: str, **valores: object) -> bool:
        """Troca o status de `de` para `para` e grava a linha no histórico.

        Devolve falso se o pedido já não estava em `de`. Conferir e trocar no
        mesmo UPDATE, como no `expire_overdue`: duas administradoras aprovando
        o mesmo comprovante ao mesmo tempo, só a primeira encontra `em_analise`
        (back-end#251).
        """
        mudou = self.db.scalar(
            update(Order)
            .where(Order.id == order_id, Order.status == de)
            .values(status=para, **valores)
            .returning(Order.id)
        )
        if mudou is None:
            return False
        self.db.add(OrderStatusHistory(order_id=order_id, status=para))
        self.db.flush()
        return True

    def add_payment(self, payment: Payment) -> Payment:
        """Um envio de comprovante. Reenviar cria linha nova (RN-22)."""
        self.db.add(payment)
        self.db.flush()
        return payment

    def latest_payment(self, order_id: int) -> Payment | None:
        """O comprovante vigente, em qualquer situação: o envio mais recente."""
        return self.db.scalar(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )

    def pending_payment(self, order_id: int) -> Payment | None:
        """O comprovante que espera validação: o envio mais recente, pendente."""
        return self.db.scalar(
            select(Payment)
            .where(Payment.order_id == order_id, Payment.status == "pendente")
            .order_by(Payment.id.desc())
            .limit(1)
        )

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
