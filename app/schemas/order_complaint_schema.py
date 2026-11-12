"""Contratos da reclamação do pedido (back-end#268).

O motivo é um dos dois da RN-77. O texto é o conteúdo da reclamação, e não
um comentário de avaliação (RN-75): obrigatório, sem espaços nas pontas.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.admin_payment_schema import QueueBuyer, QueueItem, QueueStore

ComplaintReasonName = Literal["nao_recebido", "danificado"]


class OrderComplaintCreate(BaseModel):
    reason: ComplaintReasonName
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("description", mode="before")
    @classmethod
    def sem_espacos_nas_pontas(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OrderComplaintResponse(BaseModel):
    """O que o comprador recebe de volta ao reportar."""

    id: int
    order_id: int
    reason: ComplaintReasonName
    description: str
    created_at: datetime


class ComplaintOrder(BaseModel):
    """Os dados do pedido que a administradora precisa para intermediar
    (RN-79)."""

    id: int
    # O status que o comprador vê, com as etapas simuladas.
    status: str
    store: QueueStore
    items: list[QueueItem]
    total_amount: Decimal

    @field_serializer("total_amount")
    def serializar_valor(self, valor: Decimal) -> float:
        return float(valor)


class AdminComplaintEntry(BaseModel):
    """Uma reclamação na lista da administradora (RN-78)."""

    id: int
    reason: ComplaintReasonName
    description: str
    created_at: datetime
    buyer: QueueBuyer
    order: ComplaintOrder
