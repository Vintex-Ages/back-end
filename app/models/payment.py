from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User

PaymentStatus = Literal["pendente", "aprovado", "rejeitado"]


class Payment(BaseModel):
    """Um comprovante Pix enviado para um pedido (back-end#243).

    Uma linha por envio: reenviar cria linha nova e não apaga a anterior,
    porque a RN-22 pede histórico de toda operação de pagamento. O comprovante
    vigente é o mais recente.

    A plataforma não processa o Pix (RN-13 e RN-14): o comprador paga por fora
    e anexa a imagem, que a administradora valida à mão (RN-21). Por isso não
    há id de transação nem provedor, só a chave do arquivo e o resultado da
    validação.

    Os CHECKs amarram o resultado ao status: pendente não tem validador;
    aprovado e rejeitado têm quem validou e quando; só rejeitado tem motivo, e
    nele o motivo é obrigatório (RN-23).
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente', 'aprovado', 'rejeitado')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "(status = 'pendente'"
            " AND validated_by_id IS NULL AND validated_at IS NULL)"
            " OR (status <> 'pendente'"
            " AND validated_by_id IS NOT NULL AND validated_at IS NOT NULL)",
            name="ck_payments_validation",
        ),
        CheckConstraint(
            "(status = 'rejeitado' AND rejection_reason IS NOT NULL)"
            " OR (status <> 'rejeitado' AND rejection_reason IS NULL)",
            name="ck_payments_rejection_reason",
        ),
        Index("ix_payments_order_id", "order_id"),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendente", server_default="pendente"
    )
    # Chave do arquivo no storage (`payments/receipts/...`), não URL: o
    # comprovante não é público e o upload não devolve endereço para ele
    # (back-end#220).
    receipt_key: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    validated_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)

    order: Mapped["Order"] = relationship(back_populates="payments")
    validated_by: Mapped["User | None"] = relationship()
