from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.repositories.product_repository import ProductFeedRow
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


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProductFeedItemResponse]
    page: int
    page_size: int
    total: int


class ProductAIStatusResponse(BaseModel):
    """Status da análise de IA da peça (VE-05, back-end#62).

    `not_requested` significa que a peça nunca teve fotos enviadas para
    análise; os demais valores refletem `Product.ai_status`.
    """

    status: ProductAIStatusValue
    error: str | None = None
    suggestions: ImageAnalysisResult | None = None
