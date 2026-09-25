"""Provedor real do Google AI Studio (BE-US027-1, back-end#92).

Primeira chamada real a uma API de IA no projeto — até aqui, `unavailable`
era o único provider (VE-06). Cobre só `embed`: `analyze_image` (VS-014) e
`stream_interpret_search` (VS-027) ainda não têm implementação real, então
degradam como `UnavailableAIProvider` em vez de fingir suportar algo que
não foi escrito.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from google import genai
from google.genai import types

from app.config import settings
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
    ChatTurn,
    ImageAnalysisResult,
    SearchStreamEvent,
)

_NOT_IMPLEMENTED = (
    "GoogleAIProvider ainda não implementa este método (fora do escopo do back-end#92)."
)

EMBEDDING_DIM = 768


class GoogleAIProvider(AIProvider):
    def __init__(self) -> None:
        if not settings.GOOGLE_API_KEY:
            raise AIProviderUnavailableError(
                "GOOGLE_API_KEY não configurada para AI_PROVIDER=google."
            )
        self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        raise AIProviderUnavailableError(_NOT_IMPLEMENTED)

    async def stream_interpret_search(
        self, query: str, history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[SearchStreamEvent]:
        raise AIProviderUnavailableError(_NOT_IMPLEMENTED)
        yield  # pragma: no cover - nunca alcançado; mantém a função geradora

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        # Um `types.Content` por texto: `contents=list(texts)` (strings soltas)
        # faz o SDK tratar a lista inteira como as partes de UM conteúdo só,
        # devolvendo um único vetor para todos os textos juntos — não um por
        # texto. Encapsular cada texto no seu próprio `Content` é o que faz o
        # batch devolver um vetor por entrada, na mesma ordem.
        contents = [types.Content(parts=[types.Part(text=text)]) for text in texts]
        try:
            response = self._client.models.embed_content(
                model=settings.GOOGLE_EMBEDDING_MODEL,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
            )
        except Exception as exc:  # SDK do Google não documenta uma exceção só
            raise AIProviderError(f"Falha ao gerar embedding: {exc}") from exc

        if response.embeddings is None or len(response.embeddings) != len(texts):
            raise AIProviderError(
                "Resposta de embedding do Google não tem um vetor por texto enviado."
            )
        return [list(item.values or []) for item in response.embeddings]
