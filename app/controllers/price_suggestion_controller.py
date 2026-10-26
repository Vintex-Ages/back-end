"""Sugestão de preço a partir do catálogo (BE-US018-1, back-end#254).

A regra está em `app/services/price_suggestion.py`. Aqui fica a sequência de
consultas, e nenhuma delas escreve: a sugestão não é gravada.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ErrorCode, ServiceUnavailable
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository
from app.schemas.price_suggestion_schema import (
    PriceSuggestionRequest,
    PriceSuggestionResponse,
)
from app.schemas.product_schema import ProductFilters
from app.services.ai import AIProviderError, modelo_de_embedding
from app.services.price_suggestion import (
    SEM_BASE,
    centroide,
    faixa,
    justificativa,
    palavras_do_nome,
)

logger = logging.getLogger("vintex.price_suggestion")

# Quantas peças de referência pelo nome e quantas comparáveis pelo vetor.
_REFERENCIAS = 20
_COMPARAVEIS = 10

# Do refinamento mais específico ao mais largo. A categoria nunca sai: comparar
# preço de sapato com o de acessório não diz nada sobre nenhum dos dois.
_REFINAMENTOS: tuple[tuple[str, ...], ...] = (
    ("category", "condition", "brand", "size"),
    ("category", "condition", "brand"),
    ("category", "condition"),
    ("category",),
)
_NOME_DO_CRITERIO = {
    "category": "{}",
    "condition": "{}",
    "brand": "marca {}",
    "size": "tamanho {}",
}


class PriceSuggestionController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def sugerir(self, pedido: PriceSuggestionRequest) -> PriceSuggestionResponse:
        try:
            # Só lê a configuração: nenhuma chamada ao provedor de IA.
            modelo = modelo_de_embedding()
        except AIProviderError as exc:
            logger.exception("Modelo de embedding mal configurado")
            raise ServiceUnavailable(
                "A sugestão de preço está indisponível agora.",
                code=ErrorCode.AI_UNAVAILABLE,
            ) from exc

        palavras = palavras_do_nome(pedido.name)
        referencias = self.repository.vetores_pelo_nome(
            palavras,
            modelo,
            ProductFilters(category=pedido.category),
            _REFERENCIAS,
            desempate=[
                p
                for p in palavras_do_nome(pedido.description or "")
                if p not in palavras
            ],
        )
        if not referencias:
            return _sem_base()

        posicao = centroide(referencias)
        tentados: list[dict[str, str]] = []
        for campos in _REFINAMENTOS:
            valores = {c: getattr(pedido, c) for c in campos if getattr(pedido, c)}
            # Campo não informado faz dois passos virarem a mesma consulta.
            if valores in tentados:
                continue
            tentados.append(valores)
            rows, _ = self.repository.find_similar(
                posicao,
                modelo,
                PageParams(page=1, page_size=_COMPARAVEIS),
                ProductFilters(**valores),
            )
            if len(rows) >= settings.PRICE_SUGGESTION_MIN_BASE:
                minimo, maximo = faixa([row["price"] for row in rows])
                criterios = [
                    _NOME_DO_CRITERIO[campo].format(valor)
                    for campo, valor in valores.items()
                ]
                return PriceSuggestionResponse(
                    min=minimo,
                    max=maximo,
                    justification=justificativa(minimo, maximo, len(rows), criterios),
                    based_on=len(rows),
                )
        return _sem_base()


def _sem_base() -> PriceSuggestionResponse:
    """Não inventa número: 200 com a faixa nula (back-end#254)."""
    return PriceSuggestionResponse(
        min=None, max=None, justification=SEM_BASE, based_on=0
    )
