"""Ponto único de troca de provedor de IA.

Trocar de fornecedor é registrar a nova classe em `_PROVIDERS` e apontar
`AI_PROVIDER` (env) para a chave correspondente — nenhuma feature muda
(critério de aceite da VE-06).
"""

from __future__ import annotations

from app.config import settings
from app.services.ai.base import AIProvider
from app.services.ai.google import GoogleAIProvider
from app.services.ai.unavailable import UnavailableAIProvider

_PROVIDERS: dict[str, type[AIProvider]] = {
    "unavailable": UnavailableAIProvider,
    "google": GoogleAIProvider,
}


def get_ai_provider() -> AIProvider:
    """Instancia o provider configurado em `settings.AI_PROVIDER`.

    Nome desconhecido ou não configurado cai em `UnavailableAIProvider`
    (degrada sem erro fatal, em vez de derrubar a aplicação).
    """
    provider_cls = _PROVIDERS.get(settings.AI_PROVIDER, UnavailableAIProvider)
    return provider_cls()
