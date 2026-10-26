"""Busca conversacional por similaridade (BE-US027-3, back-end#149)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import ErrorCode, ServiceUnavailable
from app.core.pagination import PageParams
from app.repositories.product_repository import ProductRepository, ProductSimilarRow
from app.schemas.chat_schema import (
    ChatErrorEvent,
    ChatEvent,
    ChatProductsEvent,
    ChatQuotaEvent,
)
from app.schemas.product_schema import ProductFeedItemResponse, ProductFilters
from app.services.ai import AIProviderError, get_ai_provider, modelo_de_embedding
from app.services.ai.base import (
    AIProvider,
    ChatTurn,
    ImageAnalysisResult,
    InterpretedQuery,
    SearchDone,
    SearchTextDelta,
)
from app.services.chat_quota import ChatQuota, CotaEsgotada

logger = logging.getLogger("vintex.assistant")

_PECAS_NO_CHAT = 5

# O que a #260 manda cortar: os filtros do catálogo (RN-40) que são atributo da
# peça (RN-49). Localização e loja ficam de fora, como no card.
_FILTROS_DO_CHAT = frozenset(
    {"category", "price_min", "price_max", "size", "brand", "condition", "color"}
)

_SEM_PERGUNTA = "Não encontrei uma pergunta pra buscar. Descreva o que você procura."
_FALHA_PROVIDER = (
    "Não conseguimos interpretar sua busca agora. Tente de novo em instantes."
)


class AssistantController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)
        self.quota = ChatQuota(db)

    def suggest_listing(
        self, image_urls: Sequence[str], label_image_url: str | None = None
    ) -> ImageAnalysisResult:
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

        A foto da etiqueta (back-end#257) vai junto, na mesma chamada: é uma
        análise só, e o prompt diz que dela saem marca, tamanho e composição.
        """
        urls = [*image_urls, label_image_url] if label_image_url else list(image_urls)
        if not urls:
            return ImageAnalysisResult()

        try:
            return get_ai_provider().analyze_image(urls)
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

        A pergunta é interpretada antes (back-end#260): o que é objetivo vira
        filtro e corta, o resto ordena por similaridade. O que foi lido vai
        para a tela no evento `interpreted`.
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
        preparo = await run_in_threadpool(self._preparar, pessoa)
        if isinstance(preparo, list):
            for event in preparo:
                yield event
            return
        provider, modelo = preparo

        interpretada = await _interpretar(provider, query, _historico(messages))
        if interpretada is not None:
            yield interpretada

        for event in await run_in_threadpool(
            self._buscar, provider, modelo, query, interpretada
        ):
            yield event

    def _preparar(self, pessoa: str) -> tuple[AIProvider, str] | list[ChatEvent]:
        """O provedor e o modelo, com a pergunta já contada na cota; ou os
        eventos que encerram a conversa."""
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
        return provider, modelo

    def _buscar(
        self,
        provider: AIProvider,
        modelo: str,
        query: str,
        interpretada: InterpretedQuery | None,
    ) -> list[ChatEvent]:
        """Filtro corta, similaridade ordena (back-end#260).

        O vetor é o da pergunta inteira, como antes. Dentro do que o filtro
        deixou passar, os atributos objetivos são iguais em todas as peças, e
        quem ordena é o resto: estilo, ocasião, descrição. E, se o filtro não
        casar com nada, é esse mesmo vetor que acha as alternativas mais
        próximas do pedido.
        """
        try:
            vectors = provider.embed([query])
        except AIProviderError:
            logger.exception("Falha ao gerar embedding da pergunta do chat")
            return [ChatErrorEvent(message=_FALHA_PROVIDER), SearchDone()]

        if not vectors:
            logger.error("Provider não devolveu vetor para a pergunta do chat")
            return [ChatErrorEvent(message=_FALHA_PROVIDER), SearchDone()]

        filtros = _filtros_da_pergunta(interpretada)
        # As mesmas cinco mais próximas de antes da paginação (back-end#246).
        pagina = PageParams(page=1, page_size=_PECAS_NO_CHAT)
        rows, _ = self.repository.find_similar(vectors[0], modelo, pagina, filtros)
        if rows or not filtros.applied():
            return [_pecas(rows, "exact"), SearchDone()]

        # Filtro sem peça nenhuma não devolve vazio (RN-61): cai nas mais
        # parecidas, e a resposta diz que são alternativas.
        for relaxado in _relaxamentos(filtros):
            rows, _ = self.repository.find_similar(vectors[0], modelo, pagina, relaxado)
            if rows:
                return [
                    SearchTextDelta(delta=_aviso_de_alternativas(filtros)),
                    _pecas(rows, "fallback"),
                    SearchDone(),
                ]
        return [_pecas([], "exact"), SearchDone()]


async def _interpretar(
    provider: AIProvider, query: str, history: Sequence[ChatTurn]
) -> InterpretedQuery | None:
    """O que a pergunta virou, ou `None` se a interpretação falhar.

    Falha aqui não derruba a conversa: a busca segue só por similaridade, como
    antes da #260. É o mesmo princípio da análise de foto (RN-57): a IA
    ajuda, mas não trava.
    """
    interpretada: InterpretedQuery | None = None
    try:
        async for event in provider.stream_interpret_search(query, history):
            if isinstance(event, InterpretedQuery):
                interpretada = event
    except AIProviderError:
        logger.warning(
            "Interpretação da pergunta falhou; busca só por similaridade",
            exc_info=True,
        )
        return None
    return interpretada


def _historico(messages: Sequence[ChatTurn]) -> list[ChatTurn]:
    """A conversa antes da pergunta atual, para "e em azul?" ter contexto."""
    for indice in range(len(messages) - 1, -1, -1):
        turno = messages[indice]
        if turno.role == "user" and turno.text.strip():
            return list(messages[:indice])
    return []


def _filtros_da_pergunta(interpretada: InterpretedQuery | None) -> ProductFilters:
    """Os filtros do catálogo que a pergunta pediu, só os que a #260 lista.
    Valor que não forma um filtro válido não entra."""
    if interpretada is None:
        return ProductFilters()
    campos = {
        campo: valor
        for campo, valor in interpretada.filters.items()
        if campo in _FILTROS_DO_CHAT
    }
    try:
        return ProductFilters.model_validate(campos)
    except PydanticValidationError:
        logger.warning("Filtros interpretados inválidos, ignorados: %s", campos)
        return ProductFilters()


def _relaxamentos(filtros: ProductFilters) -> list[ProductFilters]:
    """Do mais próximo do pedido ao catálogo inteiro.

    Primeiro só a categoria: quem pediu "bota bege" e não tem nenhuma prefere
    ver botas de outra cor a uma jaqueta. Medido com o seed: sem este passo,
    a primeira alternativa de "bota bege" era uma jaqueta jeans. Depois, o
    catálogo sem filtro, que é o último passo do feed
    (`ProductController._sem_resultado`).
    """
    passos = []
    if filtros.category and len(filtros.applied()) > 1:
        passos.append(ProductFilters(category=filtros.category))
    passos.append(ProductFilters())
    return passos


def _pecas(
    rows: Sequence[ProductSimilarRow], match_type: Literal["exact", "fallback"]
) -> ChatProductsEvent:
    return ChatProductsEvent(
        products=[ProductFeedItemResponse.from_row(row) for row in rows],
        match_type=match_type,
    )


def _aviso_de_alternativas(filtros: ProductFilters) -> str:
    """O que faltou, na ordem em que se lê um pedido: "Não encontrei peças
    com Sapatos, Verde e até R$ 400,00. Estas são alternativas..." """
    partes = [
        filtros.category,
        filtros.color,
        filtros.size and f"tamanho {filtros.size}",
        filtros.condition,
        filtros.brand and f"marca {filtros.brand}",
    ]
    if filtros.price_min is not None and filtros.price_max is not None:
        partes.append(f"de {_reais(filtros.price_min)} a {_reais(filtros.price_max)}")
    elif filtros.price_max is not None:
        partes.append(f"até {_reais(filtros.price_max)}")
    elif filtros.price_min is not None:
        partes.append(f"a partir de {_reais(filtros.price_min)}")
    pedidos = [p for p in partes if p]
    if len(pedidos) > 1:
        pedido = ", ".join(pedidos[:-1]) + " e " + pedidos[-1]
    else:
        pedido = pedidos[0]
    return (
        f"Não encontrei peças com {pedido}. Estas são alternativas, as mais "
        "parecidas com o que você pediu."
    )


def _reais(valor: Decimal) -> str:
    inteiro, centavos = f"{valor:.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"


def _last_user_message(messages: Sequence[ChatTurn]) -> str | None:
    for turn in reversed(messages):
        if turn.role == "user" and turn.text.strip():
            return turn.text
    return None
