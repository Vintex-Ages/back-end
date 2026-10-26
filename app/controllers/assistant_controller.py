"""Busca conversacional por similaridade (BE-US027-3, back-end#149)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import ErrorCode, ServiceUnavailable
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository
from app.schemas.chat_schema import (
    ChatErrorEvent,
    ChatEvent,
    ChatProductsEvent,
    ChatQuotaEvent,
)
from app.schemas.product_schema import ProductFeedItemResponse
from app.services.ai import AIProviderError, get_ai_provider, modelo_de_embedding
from app.services.ai.base import ChatTurn, ImageAnalysisResult, SearchDone
from app.services.chat_quota import ChatQuota, CotaEsgotada

logger = logging.getLogger("vintex.assistant")

_PECAS_NO_CHAT = 5

_SEM_PERGUNTA = "Não encontrei uma pergunta pra buscar. Descreva o que você procura."
_FALHA_PROVIDER = (
    "Não conseguimos interpretar sua busca agora. Tente de novo em instantes."
)


class AssistantController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)
        self.quota = ChatQuota(db)

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
                "instantes ou preencha os campos à mão.",
                code=ErrorCode.AI_UNAVAILABLE,
            ) from exc

    async def chat(
        self, messages: Sequence[ChatTurn], pessoa: str = "anonima"
    ) -> AsyncIterator[ChatEvent]:
        """Nunca inventa peça, preço ou loja (RN-65): só devolve o que `find_similar`
        acha no catálogo real. Falha do provider, pergunta ausente ou cota
        esgotada viram `error`, nunca uma exceção não tratada — a conexão sempre
        termina em `done`.

        `pessoa` é a chave da cota (back-end#258): `user:<id>` ou `ip:<origem>`.
        """
        query = _last_user_message(messages)
        if query is None:
            yield ChatErrorEvent(message=_SEM_PERGUNTA)
            yield SearchDone()
            return

        # Cota, vetor da pergunta e busca são síncronos (banco e provedor).
        # Chamados direto deste gerador `async`, seguravam o event loop:
        # enquanto o provedor respondia, nenhuma outra requisição do servidor
        # era atendida. No threadpool, como uma rota `def` comum.
        for event in await run_in_threadpool(self._responder, query, pessoa):
            yield event

    def _responder(self, query: str, pessoa: str) -> list[ChatEvent]:
        try:
            # Provedor e modelo antes da cota: erro de configuração não gasta
            # pergunta de ninguém, porque nada chegaria ao provedor.
            provider = get_ai_provider()
            modelo = modelo_de_embedding()
        except AIProviderError:
            logger.exception("Provedor de IA indisponível para o chat")
            return [ChatErrorEvent(message=_FALHA_PROVIDER), SearchDone()]

        try:
            self.quota.reservar(pessoa)
        except CotaEsgotada as cota:
            logger.info("Cota do chat esgotada (%s): %s", cota.escopo, pessoa)
            return [
                ChatQuotaEvent(message=cota.mensagem, retry_at=cota.retry_at),
                SearchDone(),
            ]

        try:
            vectors = provider.embed([query])
        except AIProviderError:
            logger.exception("Falha ao gerar embedding da pergunta do chat")
            return [ChatErrorEvent(message=_FALHA_PROVIDER), SearchDone()]

        if not vectors:
            logger.error("Provider não devolveu vetor para a pergunta do chat")
            return [ChatErrorEvent(message=_FALHA_PROVIDER), SearchDone()]

        # As mesmas cinco mais próximas de antes da paginação (back-end#246).
        # A distância já vem em cada linha; rotular direto e alternativa é a
        # `#231`, que mede o limiar.
        rows, _ = self.repository.find_similar(
            vectors[0], modelo, PageParams(page=1, page_size=_PECAS_NO_CHAT)
        )
        return [
            ChatProductsEvent(
                products=[ProductFeedItemResponse.from_row(row) for row in rows]
            ),
            SearchDone(),
        ]


def _last_user_message(messages: Sequence[ChatTurn]) -> str | None:
    for turn in reversed(messages):
        if turn.role == "user" and turn.text.strip():
            return turn.text
    return None
