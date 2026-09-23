from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, Forbidden, NotFound, ValidationError
from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_ai_correction import ProductAiCorrection
from app.models.product_image import ProductImage
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import (
    AiCorrectionResponse,
    FeedResponse,
    FeedStoreResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFeedItemResponse,
    ProductStoreResponse,
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

    def create_draft(
        self, user_id: int, data: ProductDraftCreate
    ) -> ProductDraftResponse:
        store = self.repository.get_store_for_user(user_id)
        if store is None:
            raise NotFound(
                "Você ainda não tem uma loja cadastrada.",
                code=ErrorCode.STORE_NOT_FOUND,
            )

        product = Product(
            store=store,
            name=data.name,
            description=data.description,
            category=data.category,
            style=data.style,
            brand=data.brand,
            color=data.color,
            size=data.size,
            condition=data.condition,
            price=data.price,
            status="rascunho",
            images=[
                ProductImage(image_url=url, position=position)
                for position, url in enumerate(data.images)
            ],
            ai_corrections=[
                ProductAiCorrection(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
                for correction in data.ai_corrections
            ],
        )
        self.repository.create(product)
        self.repository.commit()
        return self._to_response(product)

    def update_draft(
        self, user_id: int, product_id: int, data: ProductDraftUpdate
    ) -> ProductDraftResponse:
        product = self._get_owned_draft(user_id, product_id)

        updates = data.model_dump(
            exclude_unset=True, exclude={"images", "ai_corrections"}
        )
        for field, value in updates.items():
            setattr(product, field, value)

        if data.images is not None:
            product.images = [
                ProductImage(image_url=url, position=position)
                for position, url in enumerate(data.images)
            ]

        for correction in data.ai_corrections:
            product.ai_corrections.append(
                ProductAiCorrection(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
            )

        self.repository.commit()
        return self._to_response(product)

    def publish(self, user_id: int, product_id: int) -> ProductDraftResponse:
        product = self._get_owned_draft(user_id, product_id)

        if not product.images:
            raise ValidationError(
                "Publicar exige ao menos uma foto.",
                fields={"images": "Adicione ao menos uma foto antes de publicar."},
            )

        product.status = "ativo"
        self.repository.commit()
        return self._to_response(product)

    def _get_owned_draft(self, user_id: int, product_id: int) -> Product:
        product = self.repository.get_by_id(product_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)
        if product.store.seller.user_id != user_id:
            raise Forbidden("Esta peça não pertence à sua loja.")
        if product.status != "rascunho":
            raise Conflict("Esta peça não está em rascunho.")
        return product

    def _to_response(self, product: Product) -> ProductDraftResponse:
        store = product.store
        return ProductDraftResponse(
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
            quantity=product.quantity,
            status=product.status,
            store=ProductStoreResponse(
                id=store.id,
                name=store.name,
                city=store.address.city if store.address else None,
            ),
            images=[image.image_url for image in product.images],
            ai_corrections=[
                AiCorrectionResponse(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
                for correction in product.ai_corrections
            ],
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
