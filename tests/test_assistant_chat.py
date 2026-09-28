"""POST /api/ai/chat — busca por similaridade (BE-US027-3, back-end#149).

O SQLite não sabe comparar vetores (`cosine_distance`), então isso roda
contra Postgres de verdade: `pg_session`/`pg_client`, de `tests/conftest.py`
(#139/#161). Insere só 2-3 vetores direto no banco — não depende das 60
peças do seed, como a própria issue pede.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants.embedding import EMBEDDING_DIM
from app.controllers import assistant_controller
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from app.services.ai.base import AIProvider, AIProviderError

pytestmark = pytest.mark.postgres


def _onehot(index: int, value: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = value
    return vector


class _StubEmbeddingProvider(AIProvider):
    def __init__(self, vector: list[float]):
        self._vector = vector

    def analyze_image(self, image_urls):
        raise NotImplementedError

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        return [self._vector for _ in texts]


class _FailingProvider(AIProvider):
    def analyze_image(self, image_urls):
        raise NotImplementedError

    async def stream_interpret_search(self, query, history=()):
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):
        raise AIProviderError("cota estourada")


def _make_store(pg_session: Session, name: str) -> Store:
    user = User(
        name=f"Dona {name}",
        email=f"{name.lower()}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user, document_type="CPF", document_value=f"{hash(name) % 10**11:011d}"
    )
    store = Store(name=name, seller=seller)
    pg_session.add(store)
    pg_session.flush()
    return store


def _make_product(
    pg_session: Session, store: Store, name: str, embedding=None
) -> Product:
    from decimal import Decimal

    product = Product(
        store=store, name=name, price=Decimal("99.90"), embedding=embedding
    )
    pg_session.add(product)
    pg_session.flush()
    return product


def _sse_events(text: str) -> list[dict]:
    events = []
    for chunk in text.strip().split("\n\n"):
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[len("data: ") :]))
    return events


def test_chat_devolve_pecas_reais_ordenadas_por_semelhanca(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    store = _make_store(pg_session, "BrechoA")
    perto = _make_product(pg_session, store, "Jaqueta jeans", embedding=_onehot(0))
    longe = _make_product(pg_session, store, "Bota de couro", embedding=_onehot(1))
    sem_embedding = _make_product(
        pg_session, store, "Sem embedding ainda", embedding=None
    )
    pg_session.commit()

    query_vector = _onehot(0, 1.0)
    query_vector[1] = (
        0.1  # levemente puxado pra "longe", mas ainda mais perto de "perto"
    )
    monkeypatch.setattr(
        assistant_controller,
        "get_ai_provider",
        lambda: _StubEmbeddingProvider(query_vector),
    )

    response = pg_client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "user", "text": "procuro algo de couro"}]},
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert [e["type"] for e in events] == ["products", "done"]
    ids = [item["id"] for item in events[0]["products"]]
    assert ids == [perto.id, longe.id]  # o mais próximo primeiro
    assert sem_embedding.id not in ids  # peça sem posição nunca entra no ranking


def test_chat_catalogo_vazio_devolve_lista_vazia_sem_erro(
    pg_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        assistant_controller,
        "get_ai_provider",
        lambda: _StubEmbeddingProvider(_onehot(0)),
    )

    response = pg_client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "user", "text": "vestido de festa"}]},
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert events == [{"type": "products", "products": []}, {"type": "done"}]


def test_chat_falha_do_provider_vira_evento_de_erro_nao_500(
    pg_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        assistant_controller, "get_ai_provider", lambda: _FailingProvider()
    )

    response = pg_client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "user", "text": "qualquer coisa"}]},
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert [e["type"] for e in events] == ["error", "done"]


def test_chat_sem_mensagem_de_usuario_vira_evento_de_erro(
    pg_client: TestClient,
) -> None:
    response = pg_client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "assistant", "text": "oi, no que posso ajudar?"}]},
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert [e["type"] for e in events] == ["error", "done"]


def test_find_similar_no_repositorio_ordena_por_distancia(pg_session: Session) -> None:
    from app.repositories.product_repository import ProductRepository

    store = _make_store(pg_session, "BrechoB")
    a = _make_product(pg_session, store, "A", embedding=_onehot(0))
    b = _make_product(pg_session, store, "B", embedding=_onehot(1))
    c = _make_product(pg_session, store, "C", embedding=_onehot(2))
    pg_session.commit()

    query = _onehot(0, 1.0)
    query[1] = 0.1

    rows = ProductRepository(pg_session).find_similar(query, limit=3)

    assert [row["id"] for row in rows] == [a.id, b.id, c.id]
