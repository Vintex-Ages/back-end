"""`POST /api/products/search-by-image` (BE-US031-1, back-end#255).

A foto chega por multipart e **não é gravada**: o caminho é análise ->
texto dos atributos -> embedding -> `find_similar`, com os filtros do
catálogo somando por E.

`cosine_distance` só existe no Postgres com pgvector, então os testes que
chegam na similaridade rodam com `pg_client`/`pg_session`. Tipo e tamanho
de arquivo, cota e falha do provedor não dependem de vetor e rodam também no
SQLite, que é o outro dialeto do repositório.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.controllers import product_controller
from app.models import Address, Product, Seller, Store, User
from app.services import media_rules
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
    ImageAnalysisResult,
    ImagePhoto,
    SuggestedField,
)

ROTA = "/api/products/search-by-image"


def eixo(index: int, value: float = 1.0) -> list[float]:
    vetor = [0.0] * EMBEDDING_DIM
    vetor[index] = value
    return vetor


class _Provedor(AIProvider):
    """Dublê do provedor: registra a foto recebida e o texto vetorizado."""

    def __init__(
        self,
        analise: ImageAnalysisResult | None = None,
        vetor: list[float] | None = None,
    ) -> None:
        self.analise = (
            analise
            if analise is not None
            else ImageAnalysisResult(
                category=SuggestedField(value="Jaquetas", confidence=0.9),
                color=SuggestedField(value="Preto", confidence=0.8),
            )
        )
        self.vetor = vetor or eixo(0)
        self.fotos: list[ImagePhoto] = []
        self.textos: list[str] = []

    def analyze_image(self, image_urls):  # noqa: ANN001, ANN201
        raise AssertionError("a busca por foto não tem URL para baixar")

    def analyze_image_bytes(self, images):  # noqa: ANN001, ANN201
        self.fotos = list(images)
        return self.analise

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        raise AIProviderUnavailableError("sem interpretação")
        yield  # pragma: no cover

    def embed(self, texts):  # noqa: ANN001, ANN201
        self.textos = list(texts)
        return [self.vetor for _ in texts]


class _ProvedorFora(AIProvider):
    """O provedor não responde: é o 503 do contrato."""

    def analyze_image(self, image_urls):  # noqa: ANN001, ANN201
        raise AIProviderError("fora do ar")

    def analyze_image_bytes(self, images):  # noqa: ANN001, ANN201
        raise AIProviderError("fora do ar")

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        raise AIProviderError("fora do ar")
        yield  # pragma: no cover

    def embed(self, texts):  # noqa: ANN001, ANN201
        raise AIProviderError("fora do ar")


class _ProvedorSemVetor(_Provedor):
    def embed(self, texts):  # noqa: ANN001, ANN201
        raise AIProviderError("embedding fora do ar")


def _loja(db: Session, nome: str, cidade: str | None = None) -> Store:
    store = Store(
        name=nome,
        seller=Seller(
            user=User(name=nome, email=f"{nome.lower()}@test.local", password_hash="x"),
            document_type="CPF",
            document_value=f"{abs(hash(nome)) % 10**11:011d}",
        ),
        address=(
            Address(
                street="Rua", number="1", city=cidade, state="RS", zip_code="90000000"
            )
            if cidade
            else None
        ),
    )
    db.add(store)
    db.flush()
    return store


def _peca(
    db: Session,
    store: Store,
    nome: str,
    vetor: list[float] | None,
    *,
    categoria: str | None = None,
    preco: str = "100.00",
) -> Product:
    product = Product(
        store=store,
        name=nome,
        price=Decimal(preco),
        category=categoria,
        status="ativo",
        embedding=vetor,
        embedding_model=settings.GOOGLE_EMBEDDING_MODEL if vetor is not None else None,
    )
    db.add(product)
    db.flush()
    return product


def _buscar(
    client: TestClient,
    *,
    nome: str = "foto.jpg",
    conteudo: bytes = b"bytes-de-foto",
    tipo: str = "image/jpeg",
    **campos: str,
):
    """POST multipart com a foto e os filtros; **sem** cabeçalho de sessão."""
    return client.post(
        ROTA, files={"image": (nome, conteudo, tipo)}, data=campos or None
    )


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    p = _Provedor()
    monkeypatch.setattr(product_controller, "get_ai_provider", lambda: p)
    return p


# ---------------------------------------------------------------------------
# Sucesso e filtros (exigem pgvector)
# ---------------------------------------------------------------------------


@pytest.mark.postgres
def test_foto_de_peca_do_catalogo_traz_a_peca_entre_as_primeiras(
    pg_client: TestClient, pg_session: Session, provedor: _Provedor
) -> None:
    loja = _loja(pg_session, "Aurora")
    parecida = _peca(pg_session, loja, "Jaqueta jeans", eixo(0), categoria="Jaquetas")
    distante = _peca(pg_session, loja, "Bota de couro", eixo(1), categoria="Sapatos")
    pg_session.commit()

    resposta = _buscar(pg_client)

    assert resposta.status_code == 200
    corpo = resposta.json()
    # Deslogado (RN-26), e a mais parecida primeiro, com a distância junto.
    assert [item["id"] for item in corpo["items"]] == [parecida.id, distante.id]
    assert corpo["items"][0]["distance"] == pytest.approx(0.0, abs=1e-6)
    assert corpo["items"][1]["distance"] == pytest.approx(1.0, abs=1e-6)
    assert corpo["page"] == 1
    assert corpo["page_size"] == 20
    assert corpo["total"] == 2
    # O item é o do feed: o front usa o mesmo mapeador.
    assert corpo["items"][0]["store"] == {
        "id": loja.id,
        "name": "Aurora",
        "verified": False,
    }
    # O que a análise leu, e nada além disso (marca só com etiqueta, RN-58).
    assert corpo["interpreted"] == {
        "category": "Jaquetas",
        "color": "Preto",
        "brand": "",
    }
    # A foto foi para o provedor como bytes + tipo, sem passar por URL, e o
    # texto vetorizado são os atributos lidos.
    assert provedor.fotos == [ImagePhoto(b"bytes-de-foto", "image/jpeg")]
    assert "Jaquetas" in provedor.textos[0]
    assert "Preto" in provedor.textos[0]


@pytest.mark.postgres
def test_filtros_do_catalogo_somam_com_a_foto(
    pg_client: TestClient, pg_session: Session, provedor: _Provedor
) -> None:
    """Categoria e preço cortam junto com a semelhança, por E lógico."""
    loja = _loja(pg_session, "Aurora")
    calca_perto = _peca(
        pg_session, loja, "Calça jeans", eixo(0), categoria="Calças", preco="150.00"
    )
    _peca(pg_session, loja, "Calça cara", eixo(0), categoria="Calças", preco="500.00")
    _peca(pg_session, loja, "Jaqueta igual", eixo(0), categoria="Jaquetas")
    pg_session.commit()

    resposta = _buscar(pg_client, category="Calças", price_max="200")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["id"] for item in corpo["items"]] == [calca_perto.id]
    assert corpo["total"] == 1


@pytest.mark.postgres
def test_filtro_sem_peca_devolve_alternativas_e_nao_lista_vazia(
    pg_client: TestClient, pg_session: Session, provedor: _Provedor
) -> None:
    """RN-61: filtro que não casa relaxa, como no feed e no chat."""
    loja = _loja(pg_session, "Aurora")
    jaqueta = _peca(pg_session, loja, "Jaqueta jeans", eixo(0), categoria="Jaquetas")
    pg_session.commit()

    resposta = _buscar(pg_client, category="Sapatos")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["id"] for item in corpo["items"]] == [jaqueta.id]
    assert corpo["total"] == 1


@pytest.mark.postgres
def test_foto_sem_nada_parecido_ainda_devolve_as_mais_proximas(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """RN-61: sem limiar, uma foto ortogonal a todo o catálogo não volta vazia."""
    loja = _loja(pg_session, "Aurora")
    pecas = [_peca(pg_session, loja, f"Peça {i}", eixo(i)) for i in range(1, 4)]
    pg_session.commit()
    # O texto da análise vira um vetor ortogonal a todos os do catálogo.
    monkeypatch.setattr(
        product_controller,
        "get_ai_provider",
        lambda: _Provedor(vetor=eixo(0)),
    )

    resposta = _buscar(pg_client)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert sorted(item["id"] for item in corpo["items"]) == sorted(p.id for p in pecas)
    assert all(
        item["distance"] == pytest.approx(1.0, abs=1e-6) for item in corpo["items"]
    )


# ---------------------------------------------------------------------------
# Foto inválida, grande, provedor fora do ar (rodam também no SQLite)
# ---------------------------------------------------------------------------


def test_tipo_de_arquivo_nao_aceito_responde_415(
    client: TestClient, monkeypatch
) -> None:
    def _explode():
        raise AssertionError("tipo inválido não chega ao provedor")

    monkeypatch.setattr(product_controller, "get_ai_provider", _explode)

    resposta = _buscar(
        client, nome="nota.pdf", conteudo=b"%PDF-1.4", tipo="application/pdf"
    )

    assert resposta.status_code == 415
    assert resposta.json()["error"]["code"] == "IMAGE_INVALID_TYPE"


def test_foto_acima_do_teto_responde_413(client: TestClient, monkeypatch) -> None:
    def _explode():
        raise AssertionError("foto grande demais não chega ao provedor")

    monkeypatch.setattr(product_controller, "get_ai_provider", _explode)
    grande = b"0" * (media_rules.MAX_BYTES_PER_FILE + 1)

    resposta = _buscar(client, nome="foto-grande.jpg", conteudo=grande)

    assert resposta.status_code == 413
    assert resposta.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_foto_no_limite_de_tamanho_e_aceita(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    """8 MiB exatos passam: o teto é do contrato, e um byte além é 413."""
    db_session.add(
        Store(
            name="Sem peça",
            seller=Seller(
                user=User(name="Dona", email="dona@test.local", password_hash="x"),
                document_type="CPF",
                document_value="52998224725",
            ),
        )
    )
    db_session.commit()
    # Análise vazia: sem texto, sem vetor, a resposta é o catálogo. O que
    # este teste afirma é que a foto no limite não é recusada antes disso.
    monkeypatch.setattr(
        product_controller, "get_ai_provider", lambda: _Provedor(ImageAnalysisResult())
    )
    no_limite = b"0" * media_rules.MAX_BYTES_PER_FILE

    resposta = _buscar(client, nome="no-limite.jpg", conteudo=no_limite)

    assert resposta.status_code == 200


def test_provedor_indisponivel_responde_503(client: TestClient, monkeypatch) -> None:
    """Mesma semântica da sugestão de anúncio: falha da IA é 503, não 200 vazio."""
    monkeypatch.setattr(product_controller, "get_ai_provider", lambda: _ProvedorFora())

    resposta = _buscar(client)

    assert resposta.status_code == 503
    assert resposta.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_falha_ao_gerar_o_vetor_responde_503(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    db_session.add(
        Store(
            name="Sem peça",
            seller=Seller(
                user=User(name="Dona", email="dona@test.local", password_hash="x"),
                document_type="CPF",
                document_value="52998224725",
            ),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        product_controller, "get_ai_provider", lambda: _ProvedorSemVetor()
    )

    resposta = _buscar(client)

    assert resposta.status_code == 503
    assert resposta.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_foto_ilegivel_devolve_o_catalogo_e_nao_lista_vazia(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    """A IA respondeu e não reconheceu nada: não é erro, e não é lista vazia.

    Sem texto não há vetor, então a busca devolve o catálogo com `distance`
    nula — inventar um vetor seria apresentar ruído como semelhança.
    """
    loja = _loja(db_session, "Aurora")
    peca = _peca(db_session, loja, "Jaqueta jeans", vetor=None)
    db_session.commit()
    provedor = _Provedor(analise=ImageAnalysisResult())
    monkeypatch.setattr(product_controller, "get_ai_provider", lambda: provedor)

    resposta = _buscar(client)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["id"] for item in corpo["items"]] == [peca.id]
    assert corpo["items"][0]["distance"] is None
    assert corpo["interpreted"] == {"category": "", "color": "", "brand": ""}
    assert provedor.textos == [], "sem atributo, não há texto para vetorizar"


def test_cota_esgotada_responde_429_com_a_mesma_conta_do_chat(
    client: TestClient, monkeypatch, db_session: Session
) -> None:
    """A busca gasta o orçamento diário do provedor, como o chat (#258)."""
    db_session.add(
        Store(
            name="Sem peça",
            seller=Seller(
                user=User(name="Dona", email="dona@test.local", password_hash="x"),
                document_type="CPF",
                document_value="52998224725",
            ),
        )
    )
    db_session.commit()
    monkeypatch.setattr(settings, "CHAT_QUOTA_PER_PERSON", 1)
    monkeypatch.setattr(
        product_controller, "get_ai_provider", lambda: _Provedor(ImageAnalysisResult())
    )

    primeira = _buscar(client)
    segunda = _buscar(client)

    assert primeira.status_code == 200
    assert segunda.status_code == 429
    error = segunda.json()["error"]
    assert error["code"] == "QUOTA_EXCEEDED"
    assert "buscas por foto" in error["message"]


def test_sem_arquivo_responde_422(client: TestClient) -> None:
    resposta = client.post(ROTA, data={"category": "Jaquetas"})

    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "VALIDATION_ERROR"


def test_filtros_invalidos_explicam_o_campo(
    client: TestClient, provedor: _Provedor
) -> None:
    """`price_min > price_max` é o mesmo erro do feed, no mesmo envelope."""
    resposta = _buscar(client, price_min="500", price_max="100")

    assert resposta.status_code == 422
    error = resposta.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "price_min" in error["fields"]["body"]
