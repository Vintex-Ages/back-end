from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import (
    FeedResponse,
    FeedStoreResponse,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductFeedItemResponse,
    ProductMediaResponse,
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

    def get_detail(self, product_id: int) -> ProductDetailResponse:
        product = self.repository.get_detail_by_id(product_id)

        if product is None or product.status == "despublicado":
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        address = product.store.address

        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            category=product.category,
            style=product.style,
            brand=product.brand,
            color=product.color,
            size=product.size,
            condition=product.condition,
            price=product.price,
            status=product.status,
            city=address.city if address else None,
            state=address.state if address else None,
            media=[
                ProductMediaResponse(url=image.image_url, position=image.position)
                for image in product.images
            ],
            store=ProductDetailStoreResponse(
                id=product.store.id,
                name=product.store.name,
                logo_url=product.store.logo_url,
            ),
        )
