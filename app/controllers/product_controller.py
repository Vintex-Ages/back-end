from typing import Literal

from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode, NotFound
from app.core.pagination import Page, PageParams
from app.models.product import Product
from app.repositories.product_repository import ProductRepository
from app.schemas.product_management_schema import (
    ProductManagementPage,
    ProductManagementResponse,
    ProductUpdate,
)
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

    def list_for_seller(
        self, user_id: int, params: PageParams, status: str | None
    ) -> ProductManagementPage:
        page: Page[object] = self.repository.list_for_seller(user_id, params, status)
        return ProductManagementPage(
            items=[
                ProductManagementResponse.model_validate(product)
                for product in page.items
            ],
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )

    def update(self, product_id: int, user_id: int, data: ProductUpdate) -> Product:
        product = self._owned(product_id, user_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode ser editada.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status != "ativo":
            raise AppError(
                "Somente peças publicadas podem ser editadas.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
                status_code=409,
            )
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        return self.repository.save(product)

    def set_status(
        self,
        product_id: int,
        user_id: int,
        target_status: Literal["ativo", "despublicado"],
    ) -> Product:
        product = self._owned(product_id, user_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode mudar de situação.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        product.status = target_status
        return self.repository.save(product)

    def _owned(self, product_id: int, user_id: int) -> Product:
        product = self.repository.get_for_seller(product_id, user_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)
        return product
