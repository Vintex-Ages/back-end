from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.product_schema import (
    FeedResponse,
    FeedStoreResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductFeedItemResponse,
    SuggestionsResponse,
)
from app.services.ai.base import ImageAnalysisResult


class ProductController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def get_feed(self, params: PageParams, q: str | None = None) -> FeedResponse:
        rows, total = self.repository.get_active_feed(params, q=q)

        if q and not rows:
            return self._sem_resultado(params, q)

        return FeedResponse(
            items=self._para_itens(rows),
            page=params.page,
            page_size=params.page_size,
            total=total,
            match_type="exact",
            suggestions=None,
        )

    def _sem_resultado(self, params: PageParams, q: str) -> FeedResponse:
        """Busca sem correspondencia: devolve pecas parecidas e explica o motivo.

        Tenta cada palavra do termo isoladamente ("jaqueta jeans" vira
        "jaqueta" e depois "jeans"). Se nenhuma achar, cai para as pecas mais
        recentes, de modo que a busca nunca volta vazia enquanto houver
        catalogo. Catalogo vazio devolve vazio, sem erro.
        """
        for palavra in self._palavras(q):
            rows, _ = self.repository.get_active_feed(params, q=palavra)
            if rows:
                return self._alternativas(params, q, rows)

        rows, _ = self.repository.get_active_feed(params)
        if not rows:
            return FeedResponse(
                items=[],
                page=params.page,
                page_size=params.page_size,
                total=0,
                match_type="exact",
                suggestions=None,
            )
        return self._alternativas(params, q, rows)

    def _alternativas(
        self, params: PageParams, q: str, rows: list[ProductFeedRow]
    ) -> FeedResponse:
        return FeedResponse(
            items=[],
            page=params.page,
            page_size=params.page_size,
            total=0,
            match_type="fallback",
            suggestions=SuggestionsResponse(
                reason=f'Nenhum resultado para "{q}". Veja outras peças disponíveis.',
                items=self._para_itens(rows),
            ),
        )

    @staticmethod
    def _palavras(q: str) -> list[str]:
        """Palavras do termo com 3+ letras, so quando ha mais de uma.

        Com uma palavra so nao adianta repetir a consulta que ja falhou.
        """
        palavras = [p for p in q.split() if len(p) >= 3]
        return palavras if len(palavras) > 1 else []

    @staticmethod
    def _para_itens(rows: list[ProductFeedRow]) -> list[ProductFeedItemResponse]:
        return [
            ProductFeedItemResponse(
                id=row["id"],
                name=row["name"],
                price=row["price"],
                cover_image_url=row["cover_image_url"],
                status=row["status"],
                store=FeedStoreResponse(id=row["store_id"], name=row["store_name"]),
            )
            for row in rows
        ]

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
