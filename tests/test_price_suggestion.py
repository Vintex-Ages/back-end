"""Sugestão de preço a partir do catálogo (BE-US018-1, back-end#254).

A rota compara vetores, o que só o Postgres faz: os testes de rota rodam
contra `pg_client`. As contas (palavras, média, faixa, texto) rodam sem banco.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.controllers import price_suggestion_controller
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from app.schemas.price_suggestion_schema import (
    PriceSuggestionRequest,
    PriceSuggestionResponse,
)
from app.services import price_suggestion as regra
from app.services.ai import factory
from app.services.ai.google import GoogleAIProvider
from app.services.ai.unavailable import UnavailableAIProvider

ROTA = "/api/ai/price-suggestions"

# --- regra ------------------------------------------------------------------


def test_palavras_do_nome_sem_acento_caixa_ou_repeticao() -> None:
    assert regra.palavras_do_nome("Tênis de Corrida NIKE tênis") == [
        "tenis",
        "corrida",
        "nike",
    ]


def test_palavras_do_nome_mantem_apostrofo_da_marca() -> None:
    assert regra.palavras_do_nome("Calça Levi's 501") == ["calca", "levi's", "501"]


def test_centroide_e_a_media_de_cada_coordenada() -> None:
    assert regra.centroide([[1.0, 0.0], [0.0, 1.0], [2.0, 2.0]]) == [1.0, 1.0]


def test_faixa_e_do_primeiro_ao_terceiro_quartil() -> None:
    precos = [Decimal(p) for p in ("10", "20", "30", "40", "50")]
    assert regra.faixa(precos) == (Decimal("20.00"), Decimal("40.00"))


def test_faixa_nao_estica_por_um_preco_fora_da_curva() -> None:
    precos = [Decimal(p) for p in ("50", "55", "60", "65", "1200")]
    assert regra.faixa(precos) == (Decimal("55.00"), Decimal("65.00"))


def test_faixa_interpola_entre_vizinhos() -> None:
    precos = [Decimal("100"), Decimal("200"), Decimal("300"), Decimal("400")]
    assert regra.faixa(precos) == (Decimal("175.00"), Decimal("325.00"))


def test_justificativa_curta_em_portugues() -> None:
    texto = regra.justificativa(
        Decimal("89.9"), Decimal("1149.9"), 8, ["Roupas", "Seminovo"]
    )
    assert texto == (
        "Peças parecidas no catálogo (Roupas, Seminovo) costumam custar entre "
        "R$ 89,90 e R$ 1.149,90. Com base em 8 peças."
    )


def test_justificativa_com_um_preco_so() -> None:
    texto = regra.justificativa(Decimal("50"), Decimal("50"), 3, [])
    assert texto == (
        "Peças parecidas no catálogo costumam custar por volta de R$ 50,00. "
        "Com base em 3 peças."
    )


def test_campo_vazio_do_formulario_vale_ausente() -> None:
    pedido = PriceSuggestionRequest(name=" Jaqueta ", category="", brand="  ")
    assert pedido.name == "Jaqueta"
    assert pedido.category is None
    assert pedido.brand is None


def test_valores_saem_como_numero_no_json() -> None:
    """`Decimal` sem serializer sai como string (`#212`)."""
    corpo = json.loads(
        PriceSuggestionResponse(
            min=Decimal("89.90"), max=Decimal("149.90"), justification="x", based_on=3
        ).model_dump_json()
    )
    assert corpo["min"] == 89.9
    assert corpo["max"] == 149.9


# --- rota -------------------------------------------------------------------


def _vetor(*pesos: float) -> list[float]:
    vetor = [0.0] * EMBEDDING_DIM
    for indice, peso in enumerate(pesos):
        vetor[indice] = peso
    return vetor


@pytest.fixture
def sessao(pg_session: Session, auth_headers) -> dict[str, str]:
    user = User(name="Vendedora", email="vendedora@test.local", password_hash="x")
    pg_session.add(user)
    pg_session.commit()
    return auth_headers(user.id)


@pytest.fixture
def loja(pg_session: Session) -> Store:
    dona = User(name="Dona", email="dona@test.local", password_hash="x")
    store = Store(
        name="Brechó",
        seller=Seller(user=dona, document_type="CPF", document_value="12345678901"),
    )
    pg_session.add(store)
    pg_session.flush()
    return store


@pytest.fixture
def sem_ia(monkeypatch) -> None:
    """Qualquer chamada ao provedor de IA derruba o teste."""

    def proibido(*_args, **_kwargs):
        raise AssertionError("a sugestão de preço chamou o provedor de IA")

    monkeypatch.setattr(factory, "get_ai_provider", proibido)
    for classe in (GoogleAIProvider, UnavailableAIProvider):
        monkeypatch.setattr(classe, "embed", proibido)
        monkeypatch.setattr(classe, "analyze_image", proibido)


def _peca(
    pg_session: Session, loja: Store, nome: str, preco: str, vetor, **atributos
) -> Product:
    atributos.setdefault("category", "Roupas")
    peca = Product(
        store=loja,
        name=nome,
        price=Decimal(preco),
        status=atributos.pop("status", "ativo"),
        embedding=vetor,
        embedding_model=settings.GOOGLE_EMBEDDING_MODEL,
        **atributos,
    )
    pg_session.add(peca)
    pg_session.flush()
    return peca


@pytest.mark.postgres
def test_peca_com_semelhantes_recebe_faixa(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    for preco, peso in (("100", 0.0), ("200", 0.1), ("300", 0.2), ("400", 0.3)):
        _peca(pg_session, loja, "Jaqueta jeans", preco, _vetor(1, peso))
    _peca(pg_session, loja, "Bota de couro", "999", _vetor(0, 0, 1), category="Sapatos")
    pg_session.commit()

    resposta = pg_client.post(
        ROTA, json={"name": "Jaqueta jeans azul", "category": "Roupas"}, headers=sessao
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo == {
        "min": 175.0,
        "max": 325.0,
        "justification": (
            "Peças parecidas no catálogo (Roupas) costumam custar entre "
            "R$ 175,00 e R$ 325,00. Com base em 4 peças."
        ),
        "based_on": 4,
    }
    assert corpo["min"] < corpo["max"]


@pytest.mark.postgres
def test_based_on_e_a_contagem_das_pecas_usadas(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    """Até 10 comparáveis. Vendida, rascunho e outra categoria não contam."""
    for i in range(12):
        _peca(pg_session, loja, f"Jaqueta {i}", str(100 + i), _vetor(1, i / 100))
    _peca(pg_session, loja, "Jaqueta vendida", "5", _vetor(1), status="vendido")
    _peca(pg_session, loja, "Jaqueta rascunho", "5", _vetor(1), status="rascunho")
    _peca(pg_session, loja, "Jaqueta de sapato", "5", _vetor(1), category="Sapatos")
    pg_session.commit()

    corpo = pg_client.post(
        ROTA, json={"name": "Jaqueta", "category": "Roupas"}, headers=sessao
    ).json()

    assert corpo["based_on"] == 10
    # As 10 mais próximas custam de 100 a 109: o preço 5 não entrou.
    assert corpo["min"] >= 100


@pytest.mark.postgres
def test_peca_sem_semelhantes_recebe_faixa_nula(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    """Catálogo com base, mas nenhum nome em comum: sem referência, sem faixa.
    Pegar as peças mais próximas de nada seria inventar a comparação."""
    for preco in ("100", "200", "300"):
        _peca(pg_session, loja, "Jaqueta jeans", preco, _vetor(1))
    pg_session.commit()

    resposta = pg_client.post(ROTA, json={"name": "Vestido de festa"}, headers=sessao)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "min": None,
        "max": None,
        "justification": regra.SEM_BASE,
        "based_on": 0,
    }


@pytest.mark.postgres
@pytest.mark.parametrize(
    "atributos",
    [{"category": "Sapatos"}, {"status": "vendido"}, {"status": "rascunho"}],
    ids=["outra-categoria", "vendida", "rascunho"],
)
def test_referencia_so_vem_do_catalogo_da_categoria(
    pg_client: TestClient,
    pg_session: Session,
    loja: Store,
    sessao,
    sem_ia,
    atributos: dict,
) -> None:
    """O nome só casa com peça fora do catálogo ou de outra categoria: ela não
    serve de referência, mesmo com roupas no catálogo para comparar."""
    _peca(pg_session, loja, "Bota de couro", "900", _vetor(1), **atributos)
    for preco in ("100", "200", "300"):
        _peca(pg_session, loja, "Camiseta", preco, _vetor(1, 0.1))
    pg_session.commit()

    corpo = pg_client.post(
        ROTA, json={"name": "Bota de couro", "category": "Roupas"}, headers=sessao
    ).json()

    assert (corpo["min"], corpo["max"], corpo["based_on"]) == (None, None, 0)


@pytest.mark.postgres
def test_marca_sem_base_cai_para_conservacao_antes_da_categoria(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    _peca(
        pg_session, loja, "Jaqueta", "900", _vetor(1), condition="Usado", brand="Gucci"
    )
    for preco in ("100", "110", "120"):
        _peca(pg_session, loja, "Jaqueta", preco, _vetor(1), condition="Usado")
    for preco in ("500", "510", "520"):
        _peca(pg_session, loja, "Jaqueta", preco, _vetor(1), condition="Seminovo")
    pg_session.commit()

    corpo = pg_client.post(
        ROTA,
        json={
            "name": "Jaqueta",
            "category": "Roupas",
            "condition": "Usado",
            "brand": "Gucci",
        },
        headers=sessao,
    ).json()

    assert corpo["based_on"] == 4
    assert "(Roupas, Usado)" in corpo["justification"]


@pytest.mark.postgres
def test_abaixo_do_minimo_configurado_nao_inventa_numero(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "PRICE_SUGGESTION_MIN_BASE", 3)
    _peca(pg_session, loja, "Jaqueta A", "100", _vetor(1))
    _peca(pg_session, loja, "Jaqueta B", "200", _vetor(1, 0.1))
    pg_session.commit()

    corpo = pg_client.post(ROTA, json={"name": "Jaqueta"}, headers=sessao).json()

    assert (corpo["min"], corpo["max"], corpo["based_on"]) == (None, None, 0)

    monkeypatch.setattr(settings, "PRICE_SUGGESTION_MIN_BASE", 2)
    corpo = pg_client.post(ROTA, json={"name": "Jaqueta"}, headers=sessao).json()

    assert corpo["based_on"] == 2


@pytest.mark.postgres
def test_conservacao_refina_enquanto_sobra_base(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    for preco in ("300", "310", "320"):
        _peca(
            pg_session, loja, "Jaqueta", preco, _vetor(1), condition="Novo com etiqueta"
        )
    for preco in ("50", "60", "70"):
        _peca(pg_session, loja, "Jaqueta", preco, _vetor(1), condition="Usado")
    pg_session.commit()

    novo = pg_client.post(
        ROTA,
        json={
            "name": "Jaqueta",
            "category": "Roupas",
            "condition": "Novo com etiqueta",
        },
        headers=sessao,
    ).json()
    # Só uma peça "Seminovo" não basta: compara com a categoria inteira.
    _peca(pg_session, loja, "Jaqueta", "200", _vetor(1), condition="Seminovo")
    pg_session.commit()
    seminovo = pg_client.post(
        ROTA,
        json={"name": "Jaqueta", "category": "Roupas", "condition": "Seminovo"},
        headers=sessao,
    ).json()

    assert (novo["min"], novo["max"], novo["based_on"]) == (305.0, 315.0, 3)
    assert "(Roupas, Novo com etiqueta)" in novo["justification"]
    assert seminovo["based_on"] == 7
    assert "(Roupas)" in seminovo["justification"]


@pytest.mark.postgres
def test_nome_mais_parecido_define_a_referencia(
    pg_client: TestClient,
    pg_session: Session,
    loja: Store,
    sessao,
    sem_ia,
    monkeypatch,
) -> None:
    """ "Tênis Nike azul": a referência é o tênis Nike azul, não qualquer tênis.
    As comparáveis são as mais próximas dele no espaço vetorial.

    Com três comparáveis, a referência decide quais entram. Se fosse a média de
    todos os "tênis", os infantis entrariam na faixa."""
    monkeypatch.setattr(price_suggestion_controller, "_COMPARAVEIS", 3)
    _peca(pg_session, loja, "Tênis Nike Azul", "500", _vetor(1), category="Sapatos")
    for preco in ("450", "480"):
        _peca(
            pg_session,
            loja,
            "Tênis de corrida",
            preco,
            _vetor(1, 0.1),
            category="Sapatos",
        )
    for preco in ("40", "50", "60"):
        _peca(
            pg_session, loja, "Tênis infantil", preco, _vetor(0, 1), category="Sapatos"
        )
    pg_session.commit()

    corpo = pg_client.post(
        ROTA, json={"name": "Tênis Nike azul", "category": "Sapatos"}, headers=sessao
    ).json()

    # As três mais próximas do Nike: ele e os dois de corrida.
    assert corpo["based_on"] == 3
    assert corpo["min"] >= 450


@pytest.mark.postgres
def test_descricao_desempata_a_referencia(
    pg_client: TestClient,
    pg_session: Session,
    loja: Store,
    sessao,
    sem_ia,
    monkeypatch,
) -> None:
    """ "Jaqueta" casa igual com as duas; a descrição "jeans" escolhe. Peça que
    só casa pela descrição ("Calça jeans") não vira referência."""
    monkeypatch.setattr(price_suggestion_controller, "_COMPARAVEIS", 3)
    for preco in ("200", "210", "220"):
        _peca(pg_session, loja, "Jaqueta jeans", preco, _vetor(1))
    for preco in ("900", "910", "920"):
        _peca(pg_session, loja, "Jaqueta de couro", preco, _vetor(0, 1))
    _peca(pg_session, loja, "Calça jeans", "50", _vetor(0, 0, 1))
    pg_session.commit()

    def pedir(descricao: str) -> dict:
        return pg_client.post(
            ROTA,
            json={"name": "Jaqueta", "category": "Roupas", "description": descricao},
            headers=sessao,
        ).json()

    jeans, couro = pedir("jeans azul, pouco uso"), pedir("couro legítimo")

    assert (jeans["min"], jeans["max"]) == (205.0, 215.0)
    assert (couro["min"], couro["max"]) == (905.0, 915.0)


@pytest.mark.postgres
def test_nenhuma_escrita_no_banco(
    pg_client: TestClient, pg_session: Session, loja: Store, sessao, sem_ia
) -> None:
    for preco in ("100", "200", "300"):
        _peca(pg_session, loja, "Jaqueta", preco, _vetor(1))
    pg_session.commit()
    comandos: list[str] = []
    conexao = pg_session.connection()

    @event.listens_for(conexao, "before_cursor_execute")
    def registrar(_conn, _cursor, statement, *_args) -> None:  # noqa: ANN001
        comandos.append(statement.lstrip().split(None, 1)[0].upper())

    for _ in range(2):
        assert (
            pg_client.post(ROTA, json={"name": "Jaqueta"}, headers=sessao).status_code
            == 200
        )

    event.remove(conexao, "before_cursor_execute", registrar)
    # A sessão autenticada lê o usuário; a sugestão só lê o catálogo.
    assert comandos and set(comandos) == {"SELECT"}


@pytest.mark.postgres
def test_sem_token_responde_401(pg_client: TestClient) -> None:
    assert pg_client.post(ROTA, json={"name": "Jaqueta"}).status_code == 401


@pytest.mark.postgres
@pytest.mark.parametrize("corpo", [{}, {"name": ""}, {"name": "   "}])
def test_sem_nome_responde_422(pg_client: TestClient, sessao, corpo: dict) -> None:
    resposta = pg_client.post(ROTA, json=corpo, headers=sessao)

    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "VALIDATION_ERROR"
