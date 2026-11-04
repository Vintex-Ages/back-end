"""Contratos da administradora: validação do comprovante (back-end#251) e a
fila de comprovantes (back-end#250).

Valores em dinheiro saem como número, nunca string (#212).

A resposta de aprovar e rejeitar é parcial de propósito: só o pedido e o
pagamento que mudaram. O `adminReceiptService` do front mescla o `payment` no
item da fila que já tinha.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator


class RejectRequest(BaseModel):
    # O motivo vai para o comprador (RN-23): vazio ou só espaços não explica nada.
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def sem_espacos_nas_pontas(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ValidatedBy(BaseModel):
    id: int
    name: str


class ReviewedPayment(BaseModel):
    status: str
    validated_by: ValidatedBy
    validated_at: datetime
    # Só no reject; o approve não manda a chave.
    rejection_reason: str | None = Field(default=None)


class PaymentReviewResponse(BaseModel):
    order_id: int
    status: str
    payment: ReviewedPayment


# --- fila de comprovantes (back-end#250) -----------------------------------------


class QueueBuyer(BaseModel):
    """Contato do comprador: sem chat direto na PoC, é a administradora quem
    intermedia um pagamento duvidoso (RN-79)."""

    name: str
    email: str
    phone: str | None


class QueueStore(BaseModel):
    id: int
    name: str
    seller_name: str
    pix_key: str | None


class QueueItem(BaseModel):
    product_id: int
    name: str
    price: Decimal
    cover_image_url: str | None

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


class QueuePayment(BaseModel):
    status: str
    # A rota autenticada da administradora, nunca o prefixo público de mídia.
    receipt_url: str
    receipt_type: Literal["image", "pdf"]
    submitted_at: datetime
    validated_by: ValidatedBy | None
    validated_at: datetime | None
    # A rejeição mais recente do pedido, mesmo com um reenvio pendente: a
    # administradora vê o que já foi dito ao comprador (RN-23).
    rejection_reason: str | None


class ReceiptQueueEntry(BaseModel):
    """Um pedido na fila de validação, com o comprovante vigente."""

    order_id: int
    buyer: QueueBuyer
    store: QueueStore
    items: list[QueueItem]
    total_amount: Decimal
    platform_fee: Decimal
    # Total menos a comissão de 9%. Só exibição: a plataforma não movimenta
    # esse dinheiro, o Pix vai direto para o vendedor (RN-13, RN-19).
    seller_net_amount: Decimal
    payment: QueuePayment

    @field_serializer("total_amount", "platform_fee", "seller_net_amount")
    def serializar_valor(self, valor: Decimal) -> float:
        return float(valor)
