from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.ai.base import ImageAnalysisResult

ProductAIStatusValue = Literal[
    "not_requested", "pending", "processing", "done", "failed"
]


class FeedStoreResponse(BaseModel):
    id: int
    name: str


class ProductFeedItemResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    store: FeedStoreResponse
    status: str


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProductFeedItemResponse]
    page: int
    page_size: int
    total: int


class AiCorrectionInput(BaseModel):
    """Uma correção do vendedor sobre uma sugestão da IA, enviada pelo front."""

    field: str
    suggested: str | None = None
    final: str


class AiCorrectionResponse(BaseModel):
    field: str
    suggested: str | None
    final: str


class ProductDraftCreate(BaseModel):
    """Corpo de `POST /api/products`. Não tem `store_id` nem `quantity`:
    a loja vem de quem está criando, a quantidade é sempre 1."""

    name: str
    description: str | None = None
    category: str | None = None
    style: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    condition: str | None = None
    price: Decimal
    images: list[str] = Field(default_factory=list)
    ai_corrections: list[AiCorrectionInput] = Field(default_factory=list)


class ProductDraftUpdate(BaseModel):
    """Corpo de `PATCH /api/products/{id}`. Todo campo é opcional — só o que
    for enviado é alterado (ver `exclude_unset` no controller)."""

    name: str | None = None
    description: str | None = None
    category: str | None = None
    style: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    condition: str | None = None
    price: Decimal | None = None
    images: list[str] | None = None
    ai_corrections: list[AiCorrectionInput] = Field(default_factory=list)

    @field_validator("name", "price")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        """`name`/`price` são NOT NULL no banco: aceitamos o campo ausente
        (não altera nada), mas não `null` explícito (limparia um campo
        obrigatório e quebraria no commit)."""
        if value is None:
            raise ValueError("Este campo não pode ser definido como nulo.")
        return value


class ProductStoreResponse(BaseModel):
    id: int
    name: str
    city: str | None


class ProductDraftResponse(BaseModel):
    id: int
    name: str
    description: str | None
    category: str | None
    style: str | None
    brand: str | None
    color: str | None
    size: str | None
    condition: str | None
    price: Decimal
    quantity: int
    status: str
    store: ProductStoreResponse
    images: list[str]
    ai_corrections: list[AiCorrectionResponse]
class ProductAIStatusResponse(BaseModel):
    """Status da análise de IA da peça (VE-05, back-end#62).

    `not_requested` significa que a peça nunca teve fotos enviadas para
    análise; os demais valores refletem `Product.ai_status`.
    """

    status: ProductAIStatusValue
    error: str | None = None
    suggestions: ImageAnalysisResult | None = None
