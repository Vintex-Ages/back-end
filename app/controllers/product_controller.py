from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import (
    FeedResponse,
    FeedStoreResponse,
    ProductFeedItemResponse,
)


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
