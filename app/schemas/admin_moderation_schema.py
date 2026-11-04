"""Moderação de anúncios pela administradora (back-end#327).

O contrato é o da issue: `POST /api/admin/products/{id}/unpublish` com motivo,
`POST /api/admin/products/{id}/publish` para devolver à vitrine e
`GET /api/admin/products?moderated=true` para listar as Suspensas.

Valores em dinheiro saem como número, nunca string (#212).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator


class UnpublishRequest(BaseModel):
    """O motivo é o canal da administradora com o vendedor (RN-79).

    Vazio ou só espaços não explica nada, e o vendedor precisa dele para
    corrigir o anúncio: a validação responde 422, como o motivo da rejeição do
    comprovante.
    """

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def sem_espacos_nas_pontas(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ModerationStore(BaseModel):
    id: int
    name: str


class ModerationAuthor(BaseModel):
    """Quem tirou a peça do ar (RN-80, RN-22)."""

    id: int
    name: str


class ModerationResponse(BaseModel):
    """Resposta de suspender e de devolver à vitrine.

    Nula no motivo e na data quando a peça voltou: a moderação deixou de
    existir, e o status (`ativo`) diz o resto.
    """

    product_id: int
    status: str
    moderation_reason: str | None
    moderated_at: datetime | None


class ModeratedProductResponse(BaseModel):
    """Uma peça Suspensa na listagem da administradora."""

    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    store: ModerationStore
    moderation_reason: str
    moderated_at: datetime
    moderated_by: ModerationAuthor | None

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)
