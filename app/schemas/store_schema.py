"""Schemas da loja.

Dois conjuntos, de issues diferentes que nasceram juntas:

- **loja publica** (`GET /api/stores/{id}`, back-end#142): o que qualquer um ve.
- **loja do vendedor** (`/api/users/me/store`, back-end#141): criacao e leitura
  da propria loja, com documento e termos.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

_DOCUMENT_DIGIT_LENGTH = {"CPF": 11, "CNPJ": 14}


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


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    # Opcional: `Store.logo_url` e anulavel no modelo, e um brecho sem logo
    # ainda e um brecho. Exigir aqui impedia abrir loja, porque nao ha tela de
    # upload de logo (front-end#212 nao existe).
    logo_url: AnyHttpUrl | None = None
    document_type: Literal["CPF", "CNPJ"]
    document_value: str = Field(min_length=1, max_length=18)
    terms_version: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_document_value_length(self) -> "StoreCreate":
        digits = "".join(c for c in self.document_value if c.isdigit())
        expected = _DOCUMENT_DIGIT_LENGTH[self.document_type]
        if len(digits) != expected:
            raise ValueError(
                f"{self.document_type} deve ter {expected} dígitos "
                f"(recebeu {len(digits)})."
            )
        return self


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    name: str
    description: str | None
    logo_url: str | None
    document_type: str
    document_value: str
    terms_version: str | None
    terms_accepted_at: datetime | None
