from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.services.ai.base import ImageAnalysisResult

if TYPE_CHECKING:
    # Só para tipagem: `product_repository` importa `ProductFilters` daqui,
    # então um import de verdade em tempo de execução criaria um ciclo.
    from app.repositories.product_repository import ProductFeedRow

ProductAIStatusValue = Literal[
    "not_requested", "pending", "processing", "done", "failed"
]


class ProductFilters(BaseModel):
    category: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    size: str | None = None
    brand: str | None = None
    condition: str | None = None
    color: str | None = None

    @model_validator(mode="after")
    def validate_price_range(self) -> "ProductFilters":
        if (
            isinstance(self.price_min, Decimal)
            and isinstance(self.price_max, Decimal)
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min deve ser menor ou igual a price_max")
        return self

    def applied(self) -> dict[str, str | Decimal]:
        return {
            key: value for key, value in self.model_dump().items() if value is not None
        }


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

    @classmethod
    def from_row(cls, row: ProductFeedRow) -> "ProductFeedItemResponse":
        """Monta a partir de uma `ProductFeedRow` (feed, busca por similaridade)."""
        return cls(
            id=row["id"],
            name=row["name"],
            price=row["price"],
            cover_image_url=row["cover_image_url"],
            status=row["status"],
            store=FeedStoreResponse(id=row["store_id"], name=row["store_name"]),
        )

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


class SuggestionsResponse(BaseModel):
    reason: str
    items: list[ProductFeedItemResponse]


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProductFeedItemResponse]
    page: int
    page_size: int
    total: int
    applied_filters: dict[str, str | Decimal] = Field(default_factory=dict)
    match_type: Literal["exact", "fallback"] = "exact"
    suggestions: SuggestionsResponse | None = None


class ProductMediaResponse(BaseModel):
    type: str = "image"
    url: str
    position: int


class ProductDetailStoreResponse(FeedStoreResponse):
    logo_url: str | None
    verified: bool


class ProductDetailResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    category: str = ""
    style: str = ""
    brand: str = ""
    color: str = ""
    size: str = ""
    condition: str = ""
    price: Decimal
    status: str
    city: str = ""
    state: str = ""
    media: list[ProductMediaResponse]
    store: ProductDetailStoreResponse

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


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


class ListingSuggestionsRequest(BaseModel):
    """`POST /api/ai/listing-suggestions` (BE-US014-2, back-end#150).

    `max_length` no número de fotos: sem isso, nada impede uma lista enorme
    de URLs — cada uma baixada e mandada pra API de IA (revisão da
    Adrielle no PR #200).
    """

    image_urls: list[str] = Field(max_length=8)
