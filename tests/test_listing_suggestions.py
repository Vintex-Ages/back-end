"""`POST /api/ai/listing-suggestions` (BE-US014-2, back-end#150)."""

from collections.abc import Sequence

import pytest

from app.controllers import assistant_controller
from app.controllers.assistant_controller import AssistantController
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    ImageAnalysisResult,
    SuggestedField,
)
from app.services.ai.google import GoogleAIProvider


class _FakeOkProvider(AIProvider):
    def __init__(self) -> None:
        self.received_urls: list[str] | None = None

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        self.received_urls = list(image_urls)
        return ImageAnalysisResult(
            category=SuggestedField(value="Jaqueta", confidence=0.9),
            color=SuggestedField(value="Azul", confidence=0.8),
        )

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise NotImplementedError


class _FakeFailingProvider(AIProvider):
    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        raise AIProviderError("provedor fora do ar")

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# AssistantController.suggest_listing
# ---------------------------------------------------------------------------


def test_suggest_listing_repassa_resultado_do_provider(monkeypatch, db_session) -> None:
    fake = _FakeOkProvider()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: fake)
    controller = AssistantController(db_session)

    result = controller.suggest_listing(["https://cdn.test/foto.jpg"])

    assert result.category.value == "Jaqueta"
    assert result.color.value == "Azul"
    assert fake.received_urls == ["https://cdn.test/foto.jpg"]


def test_suggest_listing_sem_fotos_nao_chama_provider(monkeypatch, db_session) -> None:
    def _explode():
        raise AssertionError("não deveria chamar o provider sem fotos")

    monkeypatch.setattr(assistant_controller, "get_ai_provider", _explode)
    controller = AssistantController(db_session)

    result = controller.suggest_listing([])

    assert result == ImageAnalysisResult()


def test_suggest_listing_falha_do_provider_devolve_vazio_sem_travar(
    monkeypatch, db_session
) -> None:
    monkeypatch.setattr(
        assistant_controller, "get_ai_provider", lambda: _FakeFailingProvider()
    )
    controller = AssistantController(db_session)

    result = controller.suggest_listing(["https://cdn.test/foto.jpg"])

    assert result == ImageAnalysisResult()


# ---------------------------------------------------------------------------
# Rota HTTP
# ---------------------------------------------------------------------------


def test_rota_devolve_sugestoes_no_formato_esperado(client, monkeypatch) -> None:
    monkeypatch.setattr(
        assistant_controller, "get_ai_provider", lambda: _FakeOkProvider()
    )

    response = client.post(
        "/api/ai/listing-suggestions",
        json={"image_urls": ["https://cdn.test/foto.jpg"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == {"value": "Jaqueta", "confidence": 0.9}
    assert body["brand"] is None


def test_rota_falha_do_provider_devolve_200_vazio_nao_500(client, monkeypatch) -> None:
    monkeypatch.setattr(
        assistant_controller, "get_ai_provider", lambda: _FakeFailingProvider()
    )

    response = client.post(
        "/api/ai/listing-suggestions",
        json={"image_urls": ["https://cdn.test/foto.jpg"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "category": None,
        "color": None,
        "size": None,
        "condition": None,
        "description": None,
        "brand": None,
    }


def test_rota_sem_fotos_devolve_200_vazio(client) -> None:
    response = client.post("/api/ai/listing-suggestions", json={"image_urls": []})

    assert response.status_code == 200
    assert all(value is None for value in response.json().values())


def test_rota_rejeita_fotos_demais_com_422(client) -> None:
    urls = [f"https://cdn.test/foto-{i}.jpg" for i in range(9)]

    response = client.post("/api/ai/listing-suggestions", json={"image_urls": urls})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GoogleAIProvider.analyze_image
# ---------------------------------------------------------------------------


class _FakeStreamResponse:
    def __init__(
        self,
        content: bytes = b"fake-image-bytes",
        content_type: str = "image/jpeg",
        fail: bool = False,
    ):
        self._content = content
        self.headers = {"content-type": content_type}
        self._fail = fail

    def raise_for_status(self) -> None:
        if self._fail:
            import httpx

            raise httpx.HTTPStatusError("404", request=None, response=None)

    def iter_bytes(self, chunk_size: int):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc):
        return False


class _FakeHttpClient:
    def __init__(self, response: _FakeStreamResponse | None = None):
        self._response = response or _FakeStreamResponse()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def stream(self, method: str, url: str):
        return _FakeStreamContext(self._response)


class _FakeGenAIResponse:
    def __init__(self, parsed=None, text: str | None = None):
        self.parsed = parsed
        self.text = text


class _FakeGenAIModels:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeGenAIClient:
    def __init__(self, models):
        self.models = models


def _provider_with_fake_client(monkeypatch, models) -> GoogleAIProvider:
    monkeypatch.setattr("app.services.ai.google.settings.GOOGLE_API_KEY", "fake-key")
    monkeypatch.setattr(
        "app.services.ai.google.genai.Client",
        lambda **_: _FakeGenAIClient(models),
    )
    return GoogleAIProvider()


def test_analyze_image_sem_fotos_nao_chama_ninguem(monkeypatch) -> None:
    provider = _provider_with_fake_client(monkeypatch, models=None)

    result = provider.analyze_image([])

    assert result == ImageAnalysisResult()


def test_analyze_image_sucesso_usa_response_parsed(monkeypatch) -> None:
    expected = ImageAnalysisResult(
        category=SuggestedField(value="Jaqueta", confidence=0.9)
    )
    models = _FakeGenAIModels(_FakeGenAIResponse(parsed=expected))
    provider = _provider_with_fake_client(monkeypatch, models)
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client", lambda **_: _FakeHttpClient()
    )

    result = provider.analyze_image(["https://cdn.test/foto.jpg"])

    assert result is expected
    assert len(models.calls) == 1


def test_analyze_image_sem_parsed_usa_text_como_fallback(monkeypatch) -> None:
    json_payload = ImageAnalysisResult(
        color=SuggestedField(value="Azul", confidence=0.7)
    ).model_dump_json()
    models = _FakeGenAIModels(_FakeGenAIResponse(parsed=None, text=json_payload))
    provider = _provider_with_fake_client(monkeypatch, models)
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client", lambda **_: _FakeHttpClient()
    )

    result = provider.analyze_image(["https://cdn.test/foto.jpg"])

    assert result.color.value == "Azul"


def test_analyze_image_sem_parsed_nem_text_levanta(monkeypatch) -> None:
    models = _FakeGenAIModels(_FakeGenAIResponse(parsed=None, text=None))
    provider = _provider_with_fake_client(monkeypatch, models)
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client", lambda **_: _FakeHttpClient()
    )

    with pytest.raises(AIProviderError):
        provider.analyze_image(["https://cdn.test/foto.jpg"])


def test_analyze_image_falha_no_download_levanta(monkeypatch) -> None:
    provider = _provider_with_fake_client(monkeypatch, models=_FakeGenAIModels(None))
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client",
        lambda **_: _FakeHttpClient(_FakeStreamResponse(fail=True)),
    )

    with pytest.raises(AIProviderError):
        provider.analyze_image(["https://cdn.test/foto-quebrada.jpg"])


def test_analyze_image_tipo_de_arquivo_nao_suportado_levanta(monkeypatch) -> None:
    provider = _provider_with_fake_client(monkeypatch, models=_FakeGenAIModels(None))
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client",
        lambda **_: _FakeHttpClient(
            _FakeStreamResponse(content_type="application/pdf")
        ),
    )

    with pytest.raises(AIProviderError):
        provider.analyze_image(["https://cdn.test/nao-e-foto.pdf"])


def test_analyze_image_foto_grande_demais_levanta(monkeypatch) -> None:
    from app.services.ai import google as google_module

    provider = _provider_with_fake_client(monkeypatch, models=_FakeGenAIModels(None))
    conteudo_grande = b"x" * (google_module._MAX_IMAGE_BYTES + 1)
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client",
        lambda **_: _FakeHttpClient(_FakeStreamResponse(content=conteudo_grande)),
    )

    with pytest.raises(AIProviderError):
        provider.analyze_image(["https://cdn.test/foto-enorme.jpg"])


def test_analyze_image_falha_do_sdk_levanta(monkeypatch) -> None:
    class _ExplodingModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("timeout do SDK")

    provider = _provider_with_fake_client(monkeypatch, models=_ExplodingModels())
    monkeypatch.setattr(
        "app.services.ai.google.httpx.Client", lambda **_: _FakeHttpClient()
    )

    with pytest.raises(AIProviderError):
        provider.analyze_image(["https://cdn.test/foto.jpg"])
