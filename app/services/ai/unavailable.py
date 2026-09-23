"""Provider ativo enquanto nenhum fornecedor de IA foi escolhido/configurado.

Levanta `AIProviderUnavailableError` em toda chamada. Isso não é um "provider
falso": é o contrato explícito de indisponibilidade que VE-06 exige — quem
chama decide como degradar (ex.: VS-014 deixa o formulário vazio e editável).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from app.services.ai.base import (
    AIProvider,
    AIProviderUnavailableError,
    ChatTurn,
    ImageAnalysisResult,
    SearchStreamEvent,
)

_MESSAGE = "Nenhum provedor de IA está configurado (AI_PROVIDER)."


class UnavailableAIProvider(AIProvider):
    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        raise AIProviderUnavailableError(_MESSAGE)

    async def stream_interpret_search(
        self, query: str, history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[SearchStreamEvent]:
        raise AIProviderUnavailableError(_MESSAGE)
        yield  # pragma: no cover - nunca alcançado; mantém a função geradora
