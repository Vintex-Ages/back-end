"""Busca conversacional por similaridade (BE-US027-3, back-end#149)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.orm import Session

from app.core.errors import ServiceUnavailable
from app.repositories.product_repository import ProductRepository
from app.schemas.chat_schema import ChatErrorEvent, ChatEvent, ChatProductsEvent
from app.schemas.product_schema import ProductFeedItemResponse
from app.services.ai import AIProviderError, get_ai_provider
from app.services.ai.base import ChatTurn, ImageAnalysisResult, SearchDone

logger = logging.getLogger("vintex.assistant")

_SEM_PERGUNTA = "Não encontrei uma pergunta pra buscar. Descreva o que você procura."
_FALHA_PROVIDER = (
    "Não conseguimos interpretar sua busca agora. Tente de novo em instantes."
)


class AssistantController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def suggest_listing(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        """Preenchimento automático do cadastro a partir da foto (back-end#150).

        A IA não trava o cadastro (RN-57): o vendedor sempre pode preencher à
        mão. Mas falha da IA e foto ilegível são coisas diferentes, e antes as
        duas chegavam ao front idênticas — 200 com todos os campos nulos. Quem
        cadastrava lia "não identificamos nada nas fotos" enquanto o provedor
        estava fora do ar, o que joga a culpa na foto e sugere a ação errada:
        trocar a imagem em vez de tentar de novo.

        Aconteceu na primeira execução com a API real, com um 503 do Gemini por
        excesso de demanda. Agora a falha sobe como 503 `AI_UNAVAILABLE`, o
        front a distingue e diz o que de fato houve. Resultado vazio volta a
        significar só uma coisa: a IA respondeu e não reconheceu nada.
        """
        if not image_urls:
            return ImageAnalysisResult()

        try:
            return get_ai_provider().analyze_image(image_urls)
        except AIProviderError as exc:
            logger.exception("Falha ao analisar fotos para preenchimento automático")
            raise ServiceUnavailable(
                "A análise de fotos está indisponível agora. Tente de novo em "
                "instantes ou preencha os campos à mão."
            ) from exc

    async def chat(self, messages: Sequence[ChatTurn]) -> AsyncIterator[ChatEvent]:
        """Nunca inventa peça, preço ou loja (RN-65): só devolve o que `find_similar`
        acha no catálogo real. Falha do provider ou pergunta ausente vira `error`,
        nunca uma exceção não tratada — a conexão sempre termina em `done`."""
        query = _last_user_message(messages)
        if query is None:
            yield ChatErrorEvent(message=_SEM_PERGUNTA)
            yield SearchDone()
            return

        try:
            vectors = get_ai_provider().embed([query])
        except AIProviderError:
            logger.exception("Falha ao gerar embedding da pergunta do chat")
            yield ChatErrorEvent(message=_FALHA_PROVIDER)
            yield SearchDone()
            return

        if not vectors:
            logger.error("Provider não devolveu vetor para a pergunta do chat")
            yield ChatErrorEvent(message=_FALHA_PROVIDER)
            yield SearchDone()
            return

        rows = self.repository.find_similar(vectors[0])
        yield ChatProductsEvent(
            products=[ProductFeedItemResponse.from_row(row) for row in rows]
        )
        yield SearchDone()


def _last_user_message(messages: Sequence[ChatTurn]) -> str | None:
    for turn in reversed(messages):
        if turn.role == "user" and turn.text.strip():
            return turn.text
    return None
