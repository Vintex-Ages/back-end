"""`AIProvider.embed` (BE-US027-1, back-end#92)."""

from collections.abc import AsyncIterator, Sequence

import pytest

from app.constants.embedding import EMBEDDING_DIM
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
    ChatTurn,
    ImageAnalysisResult,
    SearchStreamEvent,
)
from app.services.ai.factory import _PROVIDERS, get_ai_provider
from app.services.ai.google import GoogleAIProvider
from app.services.ai.unavailable import UnavailableAIProvider


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class _FakeModels:
    """Substitui `client.models` para inspecionar como `embed` monta a chamada.

    Existe porque um bug real só apareceu contra a API de verdade: passar
    `contents=list(texts)` (strings soltas) faz o SDK tratar a lista como as
    partes de UM conteúdo só e devolver um único vetor, não um por texto.
    """

    def __init__(self, embeddings_per_call):
        self.embeddings_per_call = embeddings_per_call
        self.calls: list[list] = []

    def embed_content(self, *, model, contents, config):
        self.calls.append(contents)
        return _FakeEmbedResponse(self.embeddings_per_call)


class _FakeClient:
    def __init__(self, models):
        self.models = models


class _FakeEmbeddingProvider(AIProvider):
    """Vetor determinístico, sem chamar API nenhuma — usado nos testes."""

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        raise NotImplementedError

    async def stream_interpret_search(
        self, query: str, history: Sequence[ChatTurn] = ()
    ) -> AsyncIterator[SearchStreamEvent]:
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(text)), float(text.count(" "))] for text in texts]


def test_provider_indisponivel_levanta_no_embed() -> None:
    with pytest.raises(AIProviderUnavailableError):
        UnavailableAIProvider().embed(["jaqueta azul"])


def test_google_provider_sem_chave_levanta_na_instanciacao(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "")
    with pytest.raises(AIProviderUnavailableError):
        GoogleAIProvider()


def test_fake_embedding_provider_devolve_um_vetor_por_texto() -> None:
    provider = _FakeEmbeddingProvider()
    vectors = provider.embed(["jaqueta azul", "tênis branco"])
    assert len(vectors) == 2
    assert all(isinstance(v, list) for v in vectors)


def _vector(seed: float) -> list[float]:
    return [seed] * EMBEDDING_DIM


def test_google_embed_envia_um_content_por_texto(monkeypatch) -> None:
    from google.genai import types

    fake_models = _FakeModels(
        [_FakeEmbedding(_vector(0.1)), _FakeEmbedding(_vector(0.3))]
    )
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr(
        "app.services.ai.google.genai.Client", lambda **_: _FakeClient(fake_models)
    )
    provider = GoogleAIProvider()

    vectors = provider.embed(["jaqueta azul", "tênis branco"])

    assert vectors == [_vector(0.1), _vector(0.3)]
    sent_contents = fake_models.calls[0]
    assert len(sent_contents) == 2
    assert all(isinstance(c, types.Content) for c in sent_contents)


def test_google_embed_levanta_se_resposta_nao_bate_com_o_pedido(monkeypatch) -> None:
    fake_models = _FakeModels([_FakeEmbedding(_vector(0.1))])
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr(
        "app.services.ai.google.genai.Client", lambda **_: _FakeClient(fake_models)
    )
    provider = GoogleAIProvider()

    with pytest.raises(AIProviderError):
        provider.embed(["jaqueta azul", "tênis branco"])


def test_google_embed_levanta_se_vetor_vier_vazio(monkeypatch) -> None:
    """`values=None` (falha silenciosa do SDK) não pode virar `[]` sem erro."""
    fake_models = _FakeModels([_FakeEmbedding(None)])
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr(
        "app.services.ai.google.genai.Client", lambda **_: _FakeClient(fake_models)
    )
    provider = GoogleAIProvider()

    with pytest.raises(AIProviderError):
        provider.embed(["jaqueta azul"])


def test_google_embed_levanta_se_dimensao_vier_errada(monkeypatch) -> None:
    """Modelo devolvendo uma dimensão diferente da esperada não pode passar batido."""
    fake_models = _FakeModels([_FakeEmbedding([0.1] * 3072)])
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr(
        "app.services.ai.google.genai.Client", lambda **_: _FakeClient(fake_models)
    )
    provider = GoogleAIProvider()

    with pytest.raises(AIProviderError):
        provider.embed(["jaqueta azul"])


def test_trocar_para_google_e_so_registrar_e_apontar_a_config(monkeypatch) -> None:
    monkeypatch.setitem(_PROVIDERS, "google", GoogleAIProvider)
    monkeypatch.setattr("app.services.ai.factory.settings.AI_PROVIDER", "google")
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.ai.google.genai.Client", lambda **_: object())

    assert isinstance(get_ai_provider(), GoogleAIProvider)
