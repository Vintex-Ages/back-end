from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, Forbidden, NotFound, ValidationError
from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_ai_correction import ProductAiCorrection
from app.models.product_image import ProductImage
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.product_schema import (
    AiCorrectionResponse,
    FeedResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFeedItemResponse,
    ProductFilters,
    ProductMediaResponse,
    ProductStoreResponse,
    SuggestionsResponse,
)
from app.services.ai.base import ImageAnalysisResult


class ProductController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def get_feed(
        self, params: PageParams, filters: ProductFilters, q: str | None = None
    ) -> FeedResponse:
        rows, total = self.repository.get_active_feed(params, filters, q=q)

        if q and not rows:
            return self._sem_resultado(params, filters, q)

        return FeedResponse(
            items=[ProductFeedItemResponse.from_row(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total=total,
            applied_filters=filters.applied(),
        )

    def _sem_resultado(
        self, params: PageParams, filters: ProductFilters, q: str
    ) -> FeedResponse:
        """Busca sem correspondencia: devolve pecas parecidas e explica o motivo.

        Tenta cada palavra do termo isoladamente ("jaqueta jeans" vira
        "jaqueta" e depois "jeans"). Se nenhuma achar, cai para o catalogo
        com os mesmos filtros, de modo que a busca nunca volta vazia enquanto
        houver peca. Catalogo vazio devolve vazio, sem erro.
        """
        for palavra in self._palavras(q):
            rows, _ = self.repository.get_active_feed(params, filters, q=palavra)
            if rows:
                return self._alternativas(params, filters, q, rows)

        rows, _ = self.repository.get_active_feed(params, filters)
        if not rows:
            return FeedResponse(
                items=[],
                page=params.page,
                page_size=params.page_size,
                total=0,
                applied_filters=filters.applied(),
            )
        return self._alternativas(params, filters, q, rows)

    def _alternativas(
        self,
        params: PageParams,
        filters: ProductFilters,
        q: str,
        rows: list[ProductFeedRow],
    ) -> FeedResponse:
        return FeedResponse(
            items=[],
            page=params.page,
            page_size=params.page_size,
            # `total` conta o que esta sendo mostrado. No fallback a lista
            # exibida e `suggestions.items`, e o front faz `setTotal(total)`
            # sem olhar o `match_type` — com zero aqui, a tela diz "0 pecas
            # encontradas" em cima de uma grade cheia.
            total=len(rows),
            applied_filters=filters.applied(),
            match_type="fallback",
            suggestions=SuggestionsResponse(
                reason=f'Nenhum resultado para "{q}". Veja outras peças disponíveis.',
                items=[ProductFeedItemResponse.from_row(row) for row in rows],
            ),
        )

    @staticmethod
    def _palavras(q: str) -> list[str]:
        """Palavras do termo com 3+ letras, exceto quando repete a consulta.

        Quando so sobra uma palavra com 3+ letras e ela e o termo inteiro
        (busca de uma palavra so), nao adianta repetir a consulta que ja
        falhou. Mas um termo com duas ou mais palavras onde so uma tem 3+
        letras (ex.: "jaqueta a") ainda vale tentar isoladamente, pois e
        uma consulta diferente da original.
        """
        palavras = [p for p in q.split() if len(p) >= 3]
        if len(palavras) == 1 and palavras[0].lower() == q.strip().lower():
            return []
        return palavras

    def get_detail(self, product_id: int) -> ProductDetailResponse:
        product = self.repository.get_detail_by_id(product_id)

        if product is None or product.status == "despublicado":
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        address = product.store.address

        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            description=product.description or "",
            category=product.category or "",
            style=product.style or "",
            brand=product.brand or "",
            color=product.color or "",
            size=product.size or "",
            condition=product.condition or "",
            price=product.price,
            status=product.status,
            city=address.city if address else "",
            state=address.state if address else "",
            media=[
                ProductMediaResponse(url=image.image_url, position=image.position)
                for image in product.images
            ],
            store=ProductDetailStoreResponse(
                id=product.store.id,
                name=product.store.name,
                logo_url=product.store.logo_url,
                verified=product.store.seller.verified,
            ),
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
