from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import (
    FeedResponse,
    FeedStoreResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductFeedItemResponse,
)
from app.services.ai.base import ImageAnalysisResult


class ProductController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def get_feed(self, params: PageParams) -> FeedResponse:
        rows, total = self.repository.get_active_feed(params)
        items = [
            ProductFeedItemResponse(
                id=row["id"],
                name=row["name"],
                price=row["price"],
                cover_image_url=row["cover_image_url"],
                status=row["status"],
                store=FeedStoreResponse(
                    id=row["store_id"],
                    name=row["store_name"],
                ),
            )
            for row in rows
        ]
        return FeedResponse(
            items=items,
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def get_ai_status(self, product_id: int, user_id: int) -> ProductAIStatusResponse:
        product = self.repository.get_for_seller(product_id, user_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)

        status: ProductAIStatusValue = (
            "not_requested" if product.ai_status is None else product.ai_status
        )
        return ProductAIStatusResponse(
            status=status,
            error=product.ai_error,
            suggestions=(
                ImageAnalysisResult.model_validate(product.ai_suggestions)
                if product.ai_suggestions is not None
                else None
            ),
        )
