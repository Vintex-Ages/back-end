"""Persistência do processamento assíncrono de imagens."""

from decimal import Decimal

from app.models.product import Product
from app.models.store import Store
from app.services.ai import pipeline
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    ImageAnalysisResult,
    SuggestedField,
)
from tests.conftest import TestingSessionLocal


class _StubOkProvider(AIProvider):
    def analyze_image(self, image_urls):
        return ImageAnalysisResult(
            category=SuggestedField(value="Jaqueta", confidence=0.9)
        )

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise NotImplementedError


class _StubFailingProvider(AIProvider):
    def analyze_image(self, image_urls):
        raise AIProviderError("falha simulada do provedor")

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise NotImplementedError


class _StubCrashingProvider(AIProvider):
    def analyze_image(self, image_urls):
        raise KeyError("campo inesperado na resposta do fornecedor")

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise NotImplementedError


def make_product(db_session) -> Product:
    store = Store(seller_id=1, name="Brechó Teste")
    product = Product(store=store, name="Jaqueta", price=Decimal("99.90"))
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_process_image_analysis_persists_suggestions(db_session, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    product = make_product(db_session)

    completed = pipeline.process_image_analysis(
        product.id,
        ["https://cdn.test/foto.jpg"],
        provider=_StubOkProvider(),
    )

    db_session.refresh(product)
    assert completed is True
    assert product.ai_status == "done"
    assert product.ai_error is None
    assert product.ai_suggestions["category"]["value"] == "Jaqueta"


def test_process_image_analysis_persists_failure_and_requests_retry(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    product = make_product(db_session)

    completed = pipeline.process_image_analysis(
        product.id,
        ["https://cdn.test/foto.jpg"],
        provider=_StubFailingProvider(),
    )

    db_session.refresh(product)
    assert completed is False
    assert product.ai_status == "failed"
    assert product.ai_error
    assert product.ai_suggestions is None


def test_process_image_analysis_unexpected_failure_is_persisted(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    product = make_product(db_session)

    completed = pipeline.process_image_analysis(
        product.id,
        ["https://cdn.test/foto.jpg"],
        provider=_StubCrashingProvider(),
    )

    db_session.refresh(product)
    assert completed is False
    assert product.ai_status == "failed"
    assert product.ai_error == "Falha inesperada na análise de IA."


def test_missing_product_is_terminal_and_can_be_acknowledged(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)

    assert pipeline.process_image_analysis(999999, ["https://cdn.test/a.jpg"]) is True


def test_done_product_is_not_analyzed_twice(db_session, monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    product = make_product(db_session)
    product.ai_status = "done"
    db_session.commit()

    class _MustNotRunProvider(_StubOkProvider):
        def analyze_image(self, image_urls):
            raise AssertionError("a tarefa concluída não deve ser repetida")

    assert (
        pipeline.process_image_analysis(
            product.id,
            ["https://cdn.test/foto.jpg"],
            provider=_MustNotRunProvider(),
        )
        is True
    )
