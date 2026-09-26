"""Busca conversacional por similaridade (BE-US027-3, back-end#149)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.orm import Session

from app.repositories.product_repository import ProductRepository
from app.schemas.chat_schema import ChatErrorEvent, ChatEvent, ChatProductsEvent
from app.schemas.product_schema import ProductFeedItemResponse
from app.services.ai import AIProviderError, get_ai_provider
from app.services.ai.base import ChatTurn, SearchDone

logger = logging.getLogger("vintex.assistant")

_SEM_PERGUNTA = "Não encontrei uma pergunta pra buscar. Descreva o que você procura."
_FALHA_PROVIDER = (
    "Não conseguimos interpretar sua busca agora. Tente de novo em instantes."
)


class AssistantController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

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
