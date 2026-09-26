from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import Page, PageParams, paginate
from app.models.store import Store
from app.repositories.store_repository import StoreRepository
from app.schemas.store_schema import (
    StoreAddressResponse,
    StoreDetailResponse,
    StoreMetricsResponse,
    StoreProductItemResponse,
)


class StoreController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = StoreRepository(db)

    def get_store(self, store_id: int) -> StoreDetailResponse:
        store = self._get_or_404(store_id)
        metrics = self.repository.get_metrics(store_id)

        address = store.address
        return StoreDetailResponse(
            id=store.id,
            name=store.name,
            description=store.description,
            logo_url=store.logo_url,
            verified=store.seller.verified,
            address=(
                StoreAddressResponse(
                    street=address.street,
                    number=address.number,
                    complement=address.complement,
                    neighborhood=address.neighborhood,
                    city=address.city,
                    state=address.state,
                    zip_code=address.zip_code,
                )
                if address is not None
                else None
            ),
            metrics=StoreMetricsResponse(
                created_at=store.created_at,
                products_listed=metrics["products_listed"],
                products_sold=metrics["products_sold"],
            ),
        )

    def list_products(
        self, store_id: int, params: PageParams
    ) -> Page[StoreProductItemResponse]:
        self._get_or_404(store_id)

        stmt = self.repository.active_products_query(store_id)
        page = paginate(self.db, stmt, params)
        items = [
            StoreProductItemResponse(
                id=product.id,
                name=product.name,
                price=product.price,
                cover_image_url=(
                    product.images[0].image_url if product.images else None
                ),
                status=product.status,
            )
            for product in page.items
        ]
        return Page[StoreProductItemResponse](
            items=items, page=page.page, page_size=page.page_size, total=page.total
        )

    def _get_or_404(self, store_id: int) -> Store:
        store = self.repository.get_by_id(store_id)
        if store is None:
            raise NotFound("Loja não encontrada.", code=ErrorCode.STORE_NOT_FOUND)
        return store
