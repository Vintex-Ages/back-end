"""Abstração do provedor de IA (`app/services/ai/`, VE-06)."""

import pytest

from app.services.ai import AIProvider, AIProviderUnavailableError, get_ai_provider
from app.services.ai.factory import _PROVIDERS
from app.services.ai.unavailable import UnavailableAIProvider


def test_sem_ai_provider_configurado_cai_no_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.factory.settings.AI_PROVIDER", "unavailable")
    assert isinstance(get_ai_provider(), UnavailableAIProvider)


def test_nome_desconhecido_tambem_cai_no_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.factory.settings.AI_PROVIDER", "algum-provedor-inexistente"
    )
    assert isinstance(get_ai_provider(), UnavailableAIProvider)


def test_provider_indisponivel_nao_bloqueia_cadastro_manual() -> None:
    provider = UnavailableAIProvider()
    with pytest.raises(AIProviderUnavailableError):
        provider.analyze_image(["https://example.com/foto.jpg"])


@pytest.mark.asyncio
async def test_busca_indisponivel_nao_gera_erro_nao_tratado() -> None:
    provider = UnavailableAIProvider()
    with pytest.raises(AIProviderUnavailableError):
        async for _event in provider.stream_interpret_search("casaco preto"):
            pass


def test_trocar_provider_e_so_registrar_e_apontar_a_config(monkeypatch) -> None:
    """Simula a troca de fornecedor: nenhuma feature precisa mudar, só a config."""

    class _StubProvider(AIProvider):
        def analyze_image(self, image_urls):
            raise NotImplementedError

        async def stream_interpret_search(self, query, history=()):
            raise NotImplementedError
            yield  # pragma: no cover

    monkeypatch.setitem(_PROVIDERS, "stub", _StubProvider)
    monkeypatch.setattr("app.services.ai.factory.settings.AI_PROVIDER", "stub")

    assert isinstance(get_ai_provider(), _StubProvider)
