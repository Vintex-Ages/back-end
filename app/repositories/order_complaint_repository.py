from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.pagination import PageParams
from app.models.order import Order
from app.models.order_complaint import OrderComplaint
from app.models.seller import Seller
from app.models.store import Store


class OrderComplaintRepository:
    """Persistência das reclamações do pedido (back-end#268). Nada aqui faz
    commit."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, complaint: OrderComplaint) -> OrderComplaint:
        """O `flush` é o que bate no `UNIQUE` de `order_id`: a segunda
        reclamação no mesmo pedido levanta `IntegrityError` aqui, e o
        controller traduz."""
        self.db.add(complaint)
        self.db.flush()
        self.db.refresh(complaint)
        return complaint

    def list_all(self, params: PageParams) -> tuple[list[OrderComplaint], int]:
        """Todas as reclamações, a mais antiga primeiro, e o total. Só a rota
        da administradora chama isto (RN-78).

        Comprador, pedido, loja e vendedor vêm por join; itens e histórico (de
        onde sai o status derivado) em consulta própria por coleção. A página
        tem número fixo de consultas, qualquer que seja o tamanho dela.
        """
        total = self.db.scalar(select(func.count(OrderComplaint.id))) or 0
        complaints = self.db.scalars(
            select(OrderComplaint)
            .options(
                joinedload(OrderComplaint.author),
                joinedload(OrderComplaint.order)
                .joinedload(Order.store)
                .joinedload(Store.seller)
                .joinedload(Seller.user),
                joinedload(OrderComplaint.order).selectinload(Order.items),
                joinedload(OrderComplaint.order).selectinload(Order.status_history),
            )
            .order_by(OrderComplaint.created_at.asc(), OrderComplaint.id.asc())
            .offset(params.offset)
            .limit(params.limit)
        ).all()
        return list(complaints), total

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
