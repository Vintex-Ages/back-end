import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.controllers.order_controller import PRAZO_DO_COMPROVANTE
from app.core.clock import utcnow_naive
from app.core.errors import Conflict, ErrorCode, NotFound
from app.core.pagination import Page, PageParams
from app.models.order import Order
from app.models.payment import Payment
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.admin_payment_schema import (
    PaymentReviewResponse,
    QueueBuyer,
    QueueItem,
    QueuePayment,
    QueueStore,
    ReceiptQueueEntry,
    ReviewedPayment,
    ValidatedBy,
)
from app.services.media_storage import MediaStorage

logger = logging.getLogger(__name__)


class PaymentReviewController:
    """A administradora vê a fila (back-end#250), abre o arquivo (back-end#244)
    e aprova ou rejeita o comprovante (back-end#251).

    São as duas únicas saídas de `em_analise` (RN-82), e nenhuma é automática:
    a plataforma não processa o Pix, quem confere o arquivo é uma pessoa
    (RN-13 e RN-21). Cada ação grava quem decidiu e quando (RN-22).

    Pedido, pagamento, histórico e peças mudam no mesmo commit: não pode
    existir pedido confirmado com peça ainda reservada, nem pagamento aprovado
    com pedido em análise.
    """

    def __init__(self, db: Session):
        self.orders = OrderRepository(db)
        self.products = ProductRepository(db)

    def approve(self, order_id: int, admin: User) -> PaymentReviewResponse:
        """Confirma o pedido e a venda: a peça sai de `reservado` para `vendido`
        e passa a contar no resumo do vendedor (RN-95)."""
        agora = utcnow_naive()
        payment = self._em_analise(order_id, para="confirmado")
        payment.status = "aprovado"
        payment.validated_by_id = admin.id
        payment.validated_at = agora
        self.products.sell_for_order(order_id, sold_at=agora)
        self.orders.commit()
        return self._to_response(order_id, "confirmado", payment, admin, agora)

    def reject(self, order_id: int, admin: User, reason: str) -> PaymentReviewResponse:
        """Devolve o pedido ao comprador, com o motivo, para ele reenviar
        (RN-23). As peças continuam reservadas.

        O prazo recomeça: sem isso, um comprovante enviado no terceiro dia e
        rejeitado no quarto voltaria para `aguardando_comprovante` já vencido,
        e a expiração da #280 levaria o pedido antes do reenvio.
        """
        agora = utcnow_naive()
        payment = self._em_analise(
            order_id,
            para="aguardando_comprovante",
            expires_at=agora + PRAZO_DO_COMPROVANTE,
        )
        payment.status = "rejeitado"
        payment.rejection_reason = reason
        payment.validated_by_id = admin.id
        payment.validated_at = agora
        self.orders.commit()
        return self._to_response(
            order_id, "aguardando_comprovante", payment, admin, agora
        )

    def receipt_queue(
        self,
        params: PageParams,
        status: str | None,
        q: str | None,
        base_url: str,
    ) -> Page[ReceiptQueueEntry]:
        """A fila de validação (back-end#250): pedidos com comprovante, mais
        antigo primeiro. `base_url` monta o `receipt_url` absoluto, como a
        URL de mídia: o front pode estar em outra origem que a API."""
        orders, total = self.orders.receipt_queue(params, status, q)
        base = base_url.rstrip("/")
        return Page[ReceiptQueueEntry](
            items=[_entrada_da_fila(order, base) for order in orders],
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def read_receipt(self, order_id: int, storage: MediaStorage) -> tuple[bytes, str]:
        """Bytes e tipo do comprovante vigente do pedido (back-end#244).

        Só a administradora chega aqui (guarda do router). Comprovante de Pix
        tem dado bancário: nem o comprador dono do pedido lê o arquivo por
        aqui; ele já o tem, foi ele quem enviou.

        O tipo vem da coluna gravada no envio. Linha anterior a ela cai no
        `Content-Type` guardado no próprio objeto.
        """
        if self.orders.get(order_id) is None:
            raise NotFound("Pedido não encontrado.", code=ErrorCode.ORDER_NOT_FOUND)
        payment = self.orders.latest_payment(order_id)
        if payment is None:
            raise NotFound(
                "Este pedido ainda não tem comprovante.",
                code=ErrorCode.RECEIPT_NOT_FOUND,
            )
        try:
            conteudo, tipo_no_storage = storage.read_with_type(payment.receipt_key)
        except Exception:  # noqa: BLE001 - objeto sumido vira 404 de domínio
            logger.warning(
                "Comprovante do pedido %s não está no storage: %s",
                order_id,
                payment.receipt_key,
            )
            raise NotFound(
                "O arquivo do comprovante não foi encontrado.",
                code=ErrorCode.RECEIPT_NOT_FOUND,
            ) from None
        return conteudo, payment.receipt_content_type or tipo_no_storage

    def _em_analise(self, order_id: int, para: str, **valores: object) -> Payment:
        """Tira o pedido de `em_analise` e devolve o comprovante a validar.

        404 se o pedido não existe; 409 se ele não está em análise, inclusive
        na segunda chamada de quem clicou duas vezes ou de outra administradora.
        """
        if self.orders.get(order_id) is None:
            raise NotFound("Pedido não encontrado.", code=ErrorCode.ORDER_NOT_FOUND)

        payment = self.orders.pending_payment(order_id)
        if payment is None or not self.orders.transition(
            order_id, de="em_analise", para=para, **valores
        ):
            self.orders.rollback()
            raise Conflict(
                "Este comprovante não está mais em análise.",
                code=ErrorCode.ORDER_NOT_IN_REVIEW,
            )
        return payment

    @staticmethod
    def _to_response(
        order_id: int,
        status: str,
        payment: Payment,
        admin: User,
        validated_at: datetime,
    ) -> PaymentReviewResponse:
        return PaymentReviewResponse(
            order_id=order_id,
            status=status,
            payment=ReviewedPayment(
                status=payment.status,
                validated_by=ValidatedBy(id=admin.id, name=admin.name),
                validated_at=validated_at,
                rejection_reason=payment.rejection_reason,
            ),
        )


def _entrada_da_fila(order: Order, base_url: str) -> ReceiptQueueEntry:
    vigente = order.payments[-1]
    rejeicoes = [p for p in order.payments if p.status == "rejeitado"]
    tipo = vigente.receipt_content_type or ""
    seller = order.store.seller
    return ReceiptQueueEntry(
        order_id=order.id,
        buyer=QueueBuyer(
            name=order.buyer.name, email=order.buyer.email, phone=order.buyer.phone
        ),
        store=QueueStore(
            id=order.store.id,
            name=order.store.name,
            seller_name=seller.user.name,
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
        platform_fee=order.platform_fee,
        seller_net_amount=order.total_amount - order.platform_fee,
        payment=QueuePayment(
            status=vigente.status,
            receipt_url=f"{base_url}/api/admin/payments/{order.id}/receipt",
            # Linha anterior à coluna de tipo (#244) não tem como dizer; a
            # imagem é o caso comum, e a rota do arquivo devolve o tipo certo.
            receipt_type="pdf" if tipo == "application/pdf" else "image",
            submitted_at=vigente.submitted_at,
            validated_by=(
                ValidatedBy(id=vigente.validated_by.id, name=vigente.validated_by.name)
                if vigente.validated_by
                else None
            ),
            validated_at=vigente.validated_at,
            rejection_reason=rejeicoes[-1].rejection_reason if rejeicoes else None,
        ),
    )
