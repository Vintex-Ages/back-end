from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controllers.order_controller import status_atual
from app.core.clock import utcnow_naive
from app.core.errors import Conflict, ErrorCode, NotFound
from app.core.pagination import Page, PageParams
from app.models.order_complaint import OrderComplaint
from app.repositories.order_complaint_repository import OrderComplaintRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.admin_payment_schema import QueueBuyer, QueueItem, QueueStore
from app.schemas.order_complaint_schema import (
    AdminComplaintEntry,
    ComplaintOrder,
    OrderComplaintCreate,
    OrderComplaintResponse,
)

# Do recebimento ou da confirmação em diante (RN-77). "Não recebido" só faz
# sentido enquanto a entrega não aconteceu, então a reclamação abre já na
# aprovação do comprovante, e não só em `concluido`.
STATUS_QUE_PERMITEM_RECLAMAR = frozenset(
    {"confirmado", "preparando", "enviado", "concluido"}
)


class OrderComplaintController:
    """O comprador reporta não recebimento ou dano, e a reclamação chega à
    administradora (back-end#268).

    Sem chat direto entre comprador e vendedor, a administradora intermedia
    (RN-79). A reclamação vai só para ela e para o avaliado (RN-78): este
    controller não tem leitura para a loja nem para a peça.
    """

    def __init__(self, db: Session):
        self.complaints = OrderComplaintRepository(db)
        self.orders = OrderRepository(db)

    def report(
        self, user_id: int, order_id: int, data: OrderComplaintCreate
    ) -> OrderComplaintResponse:
        # Pedido de outra pessoa ou inexistente: a mesma resposta. Um 403
        # confirmaria que o id existe.
        order = self.orders.get_for_buyer(order_id, user_id)
        if order is None:
            raise NotFound("Pedido não encontrado.", code=ErrorCode.ORDER_NOT_FOUND)

        if status_atual(order, utcnow_naive()) not in STATUS_QUE_PERMITEM_RECLAMAR:
            raise Conflict(
                "Só dá para reportar um problema depois que o pedido é confirmado.",
                code=ErrorCode.COMPLAINT_NOT_ALLOWED,
            )

        try:
            complaint = self.complaints.add(
                OrderComplaint(
                    order_id=order.id,
                    author_id=user_id,
                    reason=data.reason,
                    description=data.description,
                )
            )
            self.complaints.commit()
        except IntegrityError:
            # O `UNIQUE` de `order_id`, e não uma consulta antes: dois cliques
            # ao mesmo tempo, só o primeiro grava.
            self.complaints.rollback()
            raise Conflict(
                "Este pedido já tem um problema reportado.",
                code=ErrorCode.ALREADY_REPORTED,
            ) from None

        return OrderComplaintResponse(
            id=complaint.id,
            order_id=complaint.order_id,
            reason=complaint.reason,  # type: ignore[arg-type]
            description=complaint.description,
            created_at=complaint.created_at,
        )

    def list_for_admin(self, params: PageParams) -> Page[AdminComplaintEntry]:
        """A lista da administradora, com os dados do pedido (RN-78, RN-79).
        A guarda de papel está no router."""
        complaints, total = self.complaints.list_all(params)
        agora = utcnow_naive()
        return Page[AdminComplaintEntry](
            items=[_entrada(c, agora) for c in complaints],
            page=params.page,
            page_size=params.page_size,
            total=total,
        )


def _entrada(complaint: OrderComplaint, agora) -> AdminComplaintEntry:
    order = complaint.order
    buyer = complaint.author
    return AdminComplaintEntry(
        id=complaint.id,
        reason=complaint.reason,  # type: ignore[arg-type]
        description=complaint.description,
        created_at=complaint.created_at,
        buyer=QueueBuyer(name=buyer.name, email=buyer.email, phone=buyer.phone),
        order=ComplaintOrder(
            id=order.id,
            status=status_atual(order, agora),
            store=QueueStore(
                id=order.store.id,
                name=order.store.name,
                seller_name=order.store.seller.user.name,
                pix_key=order.store.pix_key,
            ),
            items=[
                QueueItem(
                    product_id=item.product_id,
                    name=item.name,
                    price=item.price,
                    cover_image_url=item.cover_image_url,
                )
                for item in order.items
            ],
            total_amount=order.total_amount,
        ),
    )
