"""Pipeline assíncrono de ingestão de IA (`app/services/ai/pipeline.py`, VE-05)."""

from decimal import Decimal

from fastapi import BackgroundTasks

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


class _StubFailingProvider(AIProvider):
    def analyze_image(self, image_urls):
        raise AIProviderError("falha simulada do provedor")

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover


class _StubCrashingProvider(AIProvider):
    """Simula uma falha que não é `AIProviderError` (ex.: bug do SDK do fornecedor real)."""

    def analyze_image(self, image_urls):
        raise KeyError("campo inesperado na resposta do fornecedor")

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover


def make_product(db_session) -> Product:
    store = Store(seller_id=1, name="Brechó Teste")
    product = Product(store=store, name="Jaqueta", price=Decimal("99.90"))
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_enqueue_marca_pending_e_agenda_task(db_session) -> None:
    product = make_product(db_session)
    background_tasks = BackgroundTasks()

    pipeline.enqueue_image_analysis(
        background_tasks, product, ["https://cdn.test/foto.jpg"]
    )
    db_session.commit()

    assert product.ai_status == "pending"
    assert product.ai_error is None
    assert len(background_tasks.tasks) == 1


def test_enqueue_sem_fotos_nao_agenda_nada(db_session) -> None:
    product = make_product(db_session)
    background_tasks = BackgroundTasks()

    pipeline.enqueue_image_analysis(background_tasks, product, [])

    assert product.ai_status is None
    assert len(background_tasks.tasks) == 0


def test_run_image_analysis_sucesso_marca_done_com_sugestoes(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(pipeline, "get_ai_provider", lambda: _StubOkProvider())
    product = make_product(db_session)

    pipeline._run_image_analysis(product.id, ["https://cdn.test/foto.jpg"])

    db_session.refresh(product)
    assert product.ai_status == "done"
    assert product.ai_error is None
    assert product.ai_suggestions["category"]["value"] == "Jaqueta"


def test_run_image_analysis_falha_do_provider_marca_failed_sem_derrubar(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(pipeline, "get_ai_provider", lambda: _StubFailingProvider())
    product = make_product(db_session)

    pipeline._run_image_analysis(product.id, ["https://cdn.test/foto.jpg"])

    db_session.refresh(product)
    assert product.ai_status == "failed"
    assert product.ai_error
    assert product.ai_suggestions is None


def test_run_image_analysis_falha_inesperada_tambem_marca_failed_sem_derrubar(
    db_session, monkeypatch
) -> None:
    """Exceção que não é `AIProviderError` (ex.: fornecedor real) não deve travar a peça em `processing`."""
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(pipeline, "get_ai_provider", lambda: _StubCrashingProvider())
    product = make_product(db_session)

    pipeline._run_image_analysis(product.id, ["https://cdn.test/foto.jpg"])

    db_session.refresh(product)
    assert product.ai_status == "failed"
    assert product.ai_error == "Falha inesperada na análise de IA."
    assert product.ai_suggestions is None


def test_run_image_analysis_peca_inexistente_nao_levanta(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline, "SessionLocal", TestingSessionLocal)

    pipeline._run_image_analysis(999999, ["https://cdn.test/foto.jpg"])
