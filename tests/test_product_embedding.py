"""Coluna `Product.embedding` e o script de backfill (BE-US027-1, back-end#92)."""

from decimal import Decimal

from app.models.product import Product
from app.models.store import Store
from app.services.ai.base import AIProviderError
from scripts import backfill_embeddings
from tests.conftest import TestingSessionLocal


def make_product(
    db_session, name: str = "Jaqueta", description: str | None = "Azul, M"
) -> Product:
    store = Store(seller_id=1, name="Brechó Teste")
    product = Product(
        store=store, name=name, description=description, price=Decimal("99.90")
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_embedding_faz_round_trip_no_sqlite(db_session) -> None:
    product = make_product(db_session)
    product.embedding = [0.1, 0.2, 0.3]
    product.embedding_model = "fake-model"
    db_session.commit()
    db_session.refresh(product)

    assert product.embedding == [0.1, 0.2, 0.3]
    assert product.embedding_model == "fake-model"


class _StubProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(len(text))] for text in texts]


class _FailingProvider:
    def embed(self, texts):
        raise AIProviderError("cota estourada")


def test_backfill_preenche_pecas_pendentes(db_session, monkeypatch) -> None:
    monkeypatch.setattr(backfill_embeddings, "SessionLocal", TestingSessionLocal)
    stub = _StubProvider()
    monkeypatch.setattr(backfill_embeddings, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(
        backfill_embeddings.settings, "GOOGLE_EMBEDDING_MODEL", "modelo-x"
    )

    product = make_product(db_session)

    backfill_embeddings.run()

    db_session.refresh(product)
    assert product.embedding is not None
    assert product.embedding_model == "modelo-x"
    assert stub.calls  # o texto foi montado e enviado ao provider


def test_backfill_nao_quebra_com_peca_sem_descricao(db_session, monkeypatch) -> None:
    monkeypatch.setattr(backfill_embeddings, "SessionLocal", TestingSessionLocal)
    stub = _StubProvider()
    monkeypatch.setattr(backfill_embeddings, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(
        backfill_embeddings.settings, "GOOGLE_EMBEDDING_MODEL", "modelo-x"
    )

    product = make_product(db_session, description=None)

    backfill_embeddings.run()

    db_session.refresh(product)
    assert product.embedding is not None


def test_backfill_e_idempotente_nao_reprocessa_peca_ja_atualizada(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(backfill_embeddings, "SessionLocal", TestingSessionLocal)
    stub = _StubProvider()
    monkeypatch.setattr(backfill_embeddings, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(
        backfill_embeddings.settings, "GOOGLE_EMBEDDING_MODEL", "modelo-x"
    )

    make_product(db_session)
    backfill_embeddings.run()
    assert len(stub.calls) == 1

    backfill_embeddings.run()
    assert len(stub.calls) == 1  # segunda rodada não reprocessa nada


def test_backfill_falha_do_provider_nao_quebra_e_mantem_pendente(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(backfill_embeddings, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        backfill_embeddings, "get_ai_provider", lambda: _FailingProvider()
    )
    monkeypatch.setattr(
        backfill_embeddings.settings, "GOOGLE_EMBEDDING_MODEL", "modelo-x"
    )

    product = make_product(db_session)

    backfill_embeddings.run()

    db_session.refresh(product)
    assert product.embedding is None
