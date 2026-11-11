"""Peças que combinam com a peça aberta (BE-US030-1, back-end#328)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.product_schema import (
    CombinationItemResponse,
    CombinationsResponse,
    ProductFilters,
)

# Quantas peças o conjunto mostra. O contrato não pagina e a issue não fixa o
# número: é um conjunto para a tela da peça, não uma listagem.
LIMITE_DE_COMBINACOES = 4


class CombinationController:
    """Peças de outras categorias, ordenadas pela semelhança com a de origem.

    - **A origem só dá o vetor** (RN-63): o 404 é só para peça inexistente.
      Peça `reservado` ou `vendido` funciona igual, porque a combinação
      também aparece depois da compra.
    - **O que volta é `ativo`**, de categoria diferente da origem, e nunca
      a própria origem. Lojas diferentes são permitidas.
    - **A ordem é a semelhança** entre os vetores (RN-62), sem coocorrência de
      compra.
    - **Sem vetor, ou sem peça parecida**, vem o catálogo de outras
      categorias com `fallback`, e não lista vazia (RN-61).

    Não chama o provedor de IA: o vetor da origem já está gravado.
    """

    def __init__(self, db: Session):
        self.products = ProductRepository(db)

    def combinations(self, product_id: int) -> CombinationsResponse:
        origem = self.products.get_detail_by_id(product_id)
        if origem is None:
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        pagina = PageParams(page=1, page_size=LIMITE_DE_COMBINACOES)
        # Origem sem categoria: qualquer peça com categoria é de outra.
        categoria = origem.category or ""

        if origem.embedding is not None and origem.embedding_model:
            parecidas, _ = self.products.find_similar(
                origem.embedding,
                origem.embedding_model,
                pagina,
                exclude_category=categoria,
                exclude_product_id=origem.id,
            )
            if parecidas:
                return self._resposta(parecidas, "exact")

        catalogo, _ = self.products.get_active_feed(
            pagina,
            ProductFilters(),
            exclude_category=categoria,
            exclude_product_id=origem.id,
        )
        return self._resposta(catalogo, "fallback")

    @staticmethod
    def _resposta(
        rows: Sequence[ProductFeedRow], match_type: Literal["exact", "fallback"]
    ) -> CombinationsResponse:
        pieces = [CombinationItemResponse.from_row(row) for row in rows]
        return CombinationsResponse(
            pieces=pieces,
            match_type=match_type,
            total_amount=sum((piece.price for piece in pieces), Decimal("0")),
        )
