from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.product_schema import (
    FeedResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductFeedItemResponse,
    ProductFilters,
    ProductMediaResponse,
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
            total=0,
            applied_filters=filters.applied(),
            match_type="fallback",
            suggestions=SuggestionsResponse(
                reason=f'Nenhum resultado para "{q}". Veja outras peças disponíveis.',
                items=[ProductFeedItemResponse.from_row(row) for row in rows],
            ),
        )

    @staticmethod
    def _palavras(q: str) -> list[str]:
        """Palavras do termo com 3+ letras, so quando ha mais de uma.

        Com uma palavra so nao adianta repetir a consulta que ja falhou.
        """
        palavras = [p for p in q.split() if len(p) >= 3]
        return palavras if len(palavras) > 1 else []

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
