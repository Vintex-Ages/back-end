from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StoreAddressResponse(BaseModel):
    street: str
    number: str
    complement: str | None
    neighborhood: str | None
    city: str
    state: str
    zip_code: str


class StoreMetricsResponse(BaseModel):
    """Métricas que já existem hoje. O que não existir não entra aqui —
    o front mostra "em breve" pra qualquer coisa fora deste conjunto."""

    created_at: datetime
    products_listed: int
    products_sold: int


class StoreDetailResponse(BaseModel):
    id: int
    name: str
    description: str | None
    logo_url: str | None
    verified: bool
    address: StoreAddressResponse | None
    metrics: StoreMetricsResponse


class StoreProductItemResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
