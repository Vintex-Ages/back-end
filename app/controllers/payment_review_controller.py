import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.controllers.order_controller import PRAZO_DO_COMPROVANTE
from app.core.clock import utcnow_naive
from app.core.errors import Conflict, ErrorCode, NotFound
from app.models.payment import Payment
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.admin_payment_schema import (
    PaymentReviewResponse,
    ReviewedPayment,
    ValidatedBy,
)
from app.services.media_storage import MediaStorage

logger = logging.getLogger(__name__)


class PaymentReviewController:
    """A administradora aprova ou rejeita o comprovante (back-end#251).

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
