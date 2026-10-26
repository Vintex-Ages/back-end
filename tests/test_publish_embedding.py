"""Publicar a peça gera o vetor da busca por semelhança (back-end#245).

O vetor é gerado em segundo plano, depois da resposta, com sessão própria,
como a análise da foto. No `TestClient` a tarefa roda ao fim da requisição; a
sessão dela aponta para o banco do teste (`TestingSessionLocal`).

O provedor de IA é um dublê que gera vetor "por palavras": cada palavra do
texto acende uma posição. Texto parecido dá vetor parecido, sem rede.
"""

from __future__ import annotations

import json
import logging
import zlib
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.controllers import assistant_controller
from app.controllers.product_controller import ProductController
from app.models import Address, Product, ProductImage, Seller, Store, User
from app.services import product_embedding
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
)
from scripts import backfill_embeddings
from tests.conftest import TestingSessionLocal


def vetor_por_palavras(texto: str) -> list[float]:
    vetor = [0.0] * EMBEDDING_DIM
    for palavra in texto.lower().split():
        vetor[zlib.crc32(palavra.encode()) % EMBEDDING_DIM] += 1.0
    return vetor


class _ProviderPorPalavras(AIProvider):
    def __init__(self, falha: Exception | None = None) -> None:
        self.textos: list[str] = []
        self.falha = falha

    def analyze_image(self, image_urls):  # pragma: no cover - não usado
        raise NotImplementedError

    async def stream_interpret_search(self, query, history=()):  # pragma: no cover
        raise NotImplementedError
        yield

    def embed(self, texts):
        if self.falha:
            raise self.falha
        self.textos.extend(texts)
        return [vetor_por_palavras(texto) for texto in texts]


@pytest.fixture
def provider(monkeypatch) -> _ProviderPorPalavras:
    stub = _ProviderPorPalavras()
    monkeypatch.setattr(product_embedding, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(product_embedding, "SessionLocal", TestingSessionLocal)
    return stub


def falhando(monkeypatch, falha: Exception) -> _ProviderPorPalavras:
    stub = _ProviderPorPalavras(falha=falha)
    monkeypatch.setattr(product_embedding, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(product_embedding, "SessionLocal", TestingSessionLocal)
    return stub


def make_peca(db, status: str = "rascunho", **campos) -> Product:
    user = User(id=10, name="Dona", email="dona@test.local", password_hash="x")
    store = Store(
        name="Aurora",
        seller=Seller(user=user, document_type="CPF", document_value="52998224725"),
        address=Address(
            street="Rua",
            number="1",
            city="Porto Alegre",
            state="RS",
            zip_code="90000000",
        ),
    )
    product = Product(
        store=store,
        name=campos.pop("name", "Jaqueta jeans azul"),
        price=Decimal(campos.pop("price", "100.00")),
        status=status,
        images=[ProductImage(image_url="https://cdn.test/1.jpg", position=0)],
        **campos,
    )
    db.add(product)
    db.commit()
    return product


def publicar(client, auth_headers, product: Product):
    return client.post(
        f"/api/users/me/products/{product.id}/publish", headers=auth_headers(10)
    )


def despublicar(client, auth_headers, product: Product):
    return client.post(
        f"/api/users/me/products/{product.id}/unpublish", headers=auth_headers(10)
    )


def editar(client, auth_headers, product: Product, **campos):
    return client.patch(
        f"/api/users/me/products/{product.id}", headers=auth_headers(10), json=campos
    )


# --- publicar ---------------------------------------------------------------------


def test_publicar_grava_o_vetor_o_modelo_e_a_situacao(
    client, db_session, auth_headers, provider
):
    product = make_peca(
        db_session,
        category="Jaquetas",
        description="Lavagem clara",
        brand="Levi's",
        color="Azul",
        size="M",
        condition="Seminovo",
        style="Casual",
    )

    response = publicar(client, auth_headers, product)

    assert response.status_code == 200
    db_session.refresh(product)
    assert product.embedding is not None
    assert product.embedding_model == settings.GOOGLE_EMBEDDING_MODEL
    assert (product.embedding_status, product.embedding_error) == ("done", None)
    # Atributos da RN-49 (categoria, tamanho, cor, marca, conservação, cidade,
    # preço, descrição) mais nome e estilo.
    assert provider.textos == [
        "Jaqueta jeans azul Jaquetas Lavagem clara Levi's Azul M Seminovo Casual "
        "Porto Alegre R$ 100.00"
    ]


def test_o_vetor_e_pedido_em_segundo_plano_depois_da_publicacao(db_session, provider):
    """A publicação só marca `pending` e agenda: a IA roda depois da resposta."""
    product = make_peca(db_session)
    agendados: list[int] = []

    ProductController(db_session, agendar_embedding=agendados.append).publish(
        10, product.id
    )

    db_session.refresh(product)
    assert product.status == "ativo"
    assert (product.embedding_status, product.embedding) == ("pending", None)
    assert agendados == [product.id]
    assert provider.textos == [], "a publicação não espera a IA"


def test_backfill_e_a_publicacao_montam_o_mesmo_texto(db_session, provider):
    product = make_peca(db_session, description="Lavagem clara")

    assert backfill_embeddings.texto_da_peca(product) == (
        product_embedding.texto_da_peca(product)
    )


def test_despublicar_e_republicar_nao_perde_nem_regrava_o_vetor(
    client, db_session, auth_headers, provider
):
    product = make_peca(db_session)
    publicar(client, auth_headers, product)
    db_session.refresh(product)
    vetor = list(product.embedding)

    despublicar(client, auth_headers, product)
    db_session.refresh(product)
    assert list(product.embedding) == vetor, "despublicar não apaga o vetor (RN-52)"

    assert publicar(client, auth_headers, product).status_code == 200
    db_session.refresh(product)
    assert list(product.embedding) == vetor
    assert product.embedding_status == "done"
    assert len(provider.textos) == 1, "republicar não chama a IA de novo"


def test_republicar_com_vetor_de_outro_modelo_regrava(
    client, db_session, auth_headers, provider
):
    product = make_peca(
        db_session,
        status="despublicado",
        embedding=[0.5] * EMBEDDING_DIM,
        embedding_model="modelo-antigo",
    )

    publicar(client, auth_headers, product)

    db_session.refresh(product)
    assert product.embedding_model == settings.GOOGLE_EMBEDDING_MODEL
    assert len(provider.textos) == 1


# --- falha da IA não bloqueia, e fica registrada ----------------------------------


def test_falha_do_provedor_nao_impede_a_publicacao_e_fica_registrada(
    client, db_session, auth_headers, monkeypatch, caplog
):
    """Como a análise da foto: situação `failed` e o motivo na peça."""
    falhando(monkeypatch, AIProviderError("503 UNAVAILABLE"))
    product = make_peca(db_session)

    with caplog.at_level(logging.WARNING, logger="app.services.product_embedding"):
        response = publicar(client, auth_headers, product)

    assert response.status_code == 200
    db_session.refresh(product)
    assert product.status == "ativo"
    assert product.embedding is None and product.embedding_model is None
    assert product.embedding_status == "failed"
    assert product.embedding_error == (
        "Provedor de IA indisponível ou falhou ao gerar o vetor."
    )
    assert f"Peça {product.id} ficou sem vetor" in caplog.text


def test_erro_inesperado_do_provedor_tambem_nao_impede(
    client, db_session, auth_headers, monkeypatch
):
    falhando(monkeypatch, RuntimeError("timeout de rede"))
    product = make_peca(db_session)

    assert publicar(client, auth_headers, product).status_code == 200
    db_session.refresh(product)
    assert (product.status, product.embedding_status) == ("ativo", "failed")


def test_sem_ia_configurada_publica_e_registra_sem_alarme(
    client, db_session, auth_headers, monkeypatch, caplog
):
    """Como na staging hoje (`AI_PROVIDER=unavailable`)."""
    falhando(monkeypatch, AIProviderUnavailableError("sem provedor"))
    product = make_peca(db_session)

    with caplog.at_level(logging.INFO, logger="app.services.product_embedding"):
        response = publicar(client, auth_headers, product)

    assert response.status_code == 200
    db_session.refresh(product)
    assert product.embedding_status == "failed"
    assert product.embedding_error == (
        "Nenhum provedor de IA configurado para gerar o vetor."
    )
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_lista_de_modelos_e_recusada_e_a_peca_publica_sem_vetor(
    client, db_session, auth_headers, provider, monkeypatch
):
    monkeypatch.setattr(settings, "GOOGLE_EMBEDDING_MODEL", "modelo-a,modelo-b")
    product = make_peca(db_session)

    assert publicar(client, auth_headers, product).status_code == 200
    db_session.refresh(product)
    assert product.embedding is None and product.embedding_model is None
    assert product.embedding_status == "failed"
    assert provider.textos == [], "nem chegou a chamar o provedor"


def test_backfill_recupera_a_peca_que_falhou(
    client, db_session, auth_headers, monkeypatch
):
    stub = falhando(monkeypatch, AIProviderError("503"))
    product = make_peca(db_session)
    publicar(client, auth_headers, product)
    stub.falha = None
    monkeypatch.setattr(backfill_embeddings, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(backfill_embeddings, "get_ai_provider", lambda: stub)

    backfill_embeddings.run()

    db_session.refresh(product)
    assert product.embedding is not None
    assert (product.embedding_status, product.embedding_error) == ("done", None)


# --- editar -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, valor",
    [("color", "Azul escuro"), ("price", "150.00"), ("condition", "Usado")],
)
def test_editar_atributo_do_texto_numa_peca_ativa_regrava_o_vetor(
    client, db_session, auth_headers, provider, campo, valor
):
    product = make_peca(db_session)
    publicar(client, auth_headers, product)
    db_session.refresh(product)
    antes = list(product.embedding)

    response = editar(client, auth_headers, product, **{campo: valor})

    assert response.status_code == 200
    db_session.refresh(product)
    assert list(product.embedding) != antes
    assert product.embedding_status == "done"
    assert len(provider.textos) == 2


def test_editar_so_as_fotos_nao_chama_a_ia(client, db_session, auth_headers, provider):
    product = make_peca(db_session)
    publicar(client, auth_headers, product)

    editar(client, auth_headers, product, images=["https://cdn.test/2.jpg"])

    assert len(provider.textos) == 1


def test_editar_texto_de_peca_despublicada_apaga_e_republicar_regrava(
    client, db_session, auth_headers, provider
):
    product = make_peca(db_session)
    publicar(client, auth_headers, product)
    despublicar(client, auth_headers, product)

    editar(client, auth_headers, product, name="Jaqueta de couro")
    db_session.refresh(product)
    assert product.embedding is None, "o vetor antigo descreveria a peça de antes"
    assert product.embedding_status is None
    assert len(provider.textos) == 1, "fora do ar, não gasta IA ao editar"

    publicar(client, auth_headers, product)
    db_session.refresh(product)
    assert product.embedding_status == "done"
    assert provider.textos[-1].startswith("Jaqueta de couro")


def test_falha_ao_regravar_tira_o_vetor_antigo(
    client, db_session, auth_headers, provider
):
    """Sem vetor, o backfill encontra a peça depois; com o antigo, não."""
    product = make_peca(db_session)
    publicar(client, auth_headers, product)
    provider.falha = AIProviderError("503")

    assert editar(client, auth_headers, product, name="Saia longa").status_code == 200
    db_session.refresh(product)
    assert product.name == "Saia longa"
    assert product.embedding is None
    assert product.embedding_status == "failed"


# --- a peça publicada aparece na busca por significado ----------------------------


@pytest.mark.postgres
def test_peca_publicada_aparece_no_chat_por_significado(
    pg_client, pg_session, auth_headers, monkeypatch
):
    stub = _ProviderPorPalavras()
    monkeypatch.setattr(product_embedding, "get_ai_provider", lambda: stub)
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: stub)
    # A tarefa em segundo plano abre sessão própria; no teste, ela entra na
    # mesma transação do `pg_session`, que é desfeita no fim.
    monkeypatch.setattr(
        product_embedding,
        "SessionLocal",
        lambda: Session(
            bind=pg_session.connection(), join_transaction_mode="create_savepoint"
        ),
    )
    publicada = make_peca(pg_session, name="Jaqueta jeans azul", description="Levi's")
    pg_session.add(
        Product(
            store=publicada.store,
            name="Vestido floral",
            price=Decimal("80.00"),
            status="ativo",
            embedding=vetor_por_palavras("Vestido floral"),
            embedding_model=settings.GOOGLE_EMBEDDING_MODEL,
        )
    )
    pg_session.commit()

    response = pg_client.post(
        f"/api/users/me/products/{publicada.id}/publish", headers=auth_headers(10)
    )
    assert response.status_code == 200
    resposta = pg_client.post(
        "/api/ai/chat", json={"messages": [{"role": "user", "text": "jaqueta jeans"}]}
    )

    eventos = [
        json.loads(bloco[len("data: ") :])
        for bloco in resposta.text.strip().split("\n\n")
        if bloco.startswith("data: ")
    ]
    assert eventos[0]["type"] == "products"
    ids = [item["id"] for item in eventos[0]["products"]]
    assert ids[0] == publicada.id, "a peça recém-publicada vem primeiro"
