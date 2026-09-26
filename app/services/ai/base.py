"""Abstração do provedor de IA (VE-06).

Nenhuma feature deve chamar um SDK de IA diretamente: toda integração passa
por `AIProvider`. Trocar de fornecedor é implementar uma nova subclasse e
apontar `AI_PROVIDER` (`app/config.py`) para ela — nenhuma feature muda.

Só cobre os usos já confirmados por uma issue em andamento (análise de
imagem para VS-014, busca conversacional para VS-027). Recomendação,
sugestão de preço e personalidade entram na interface quando a issue
correspondente definir o contrato de entrada/saída — declará-los antes
disso seria inventar um contrato sem consumidor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Literal

from pydantic import BaseModel


class AIProviderError(Exception):
    """Falha do provedor de IA. Nunca deve virar um 500 não tratado.

    Quem chama um `AIProvider` (controller ou pipeline) captura isto e
    degrada a funcionalidade (ex.: formulário fica vazio e editável, busca
    volta um resultado vazio) — nunca deixa a exceção subir sem tratamento.
    """


class AIProviderUnavailableError(AIProviderError):
    """Nenhum provedor está configurado, ou o provedor configurado falhou."""


class SuggestedField(BaseModel):
    """Um campo sugerido pela IA a partir da imagem (VS-014).

    `confidence` é opcional porque nem todo provedor expõe uma pontuação.
    """

    value: str
    confidence: float | None = None


class ImageAnalysisResult(BaseModel):
    """Sugestões extraídas de uma ou mais fotos de uma peça (VS-014).

    Cada campo é `None` quando o provedor não conseguiu sugerir aquele
    atributo especificamente — não quando a chamada inteira falhou (nesse
    caso o provider levanta `AIProviderError`).
    """

    category: SuggestedField | None = None
    color: SuggestedField | None = None
    size: SuggestedField | None = None
    condition: SuggestedField | None = None
    description: SuggestedField | None = None


class ChatTurn(BaseModel):
    """Uma mensagem do histórico da conversa, para dar contexto à busca."""

    role: Literal["user", "assistant"]
    text: str


class SearchTextDelta(BaseModel):
    """Pedaço de texto da resposta em streaming (VS-027)."""

    type: Literal["text"] = "text"
    delta: str


class InterpretedQuery(BaseModel):
    """O que a pergunta virou: objetivo → filtro, subjetivo → similaridade.

    `filters` usa os mesmos nomes de campo do catálogo (`category`,
    `price_max`, ...) para o controller poder repassar direto ao
    `product_repository` — a IA não consulta o catálogo, só interpreta.
    """

    type: Literal["interpreted"] = "interpreted"
    filters: dict[str, str] = {}
    similarity: str | None = None


class SearchDone(BaseModel):
    type: Literal["done"] = "done"


SearchStreamEvent = SearchTextDelta | InterpretedQuery | SearchDone


class AIProvider(ABC):
    """Interface única para os usos de IA do Vintex.

    Implementações concretas (um fornecedor real) entram como subclasses
    quando o time escolher o modelo. Até lá, `UnavailableAIProvider`
    (`app/services/ai/unavailable.py`) é o provider ativo por padrão.
    """

    @abstractmethod
    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        """Sugere atributos da peça a partir das fotos (VS-014, VE-05)."""

    @abstractmethod
    def stream_interpret_search(
        self, query: str, history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[SearchStreamEvent]:
        """Interpreta a busca em linguagem natural, em streaming (VS-027).

        Emite texto (`SearchTextDelta`) e a interpretação da pergunta
        (`InterpretedQuery`), terminando em `SearchDone`. Nunca inclui
        peças: quem busca no catálogo real é o controller, usando
        `InterpretedQuery.filters`/`similarity` (RN-65 — a IA não inventa
        peça, preço ou loja).
        """

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Gera um vetor por texto de entrada (BE-US027-1, back-end#92).

        Base da busca por similaridade (VS-027): cada peça vira uma posição
        num espaço vetorial, e "achar parecido" vira uma consulta de
        distância nesse espaço (`Product.embedding`). Devolve um vetor por
        texto, na mesma ordem de `texts`.
        """
