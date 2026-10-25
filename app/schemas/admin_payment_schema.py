"""Contratos da validação do comprovante pela administradora (back-end#251).

A resposta é parcial de propósito: só o pedido e o pagamento que mudaram. O
`adminReceiptService` do front mescla o `payment` no item da fila que já tinha.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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
