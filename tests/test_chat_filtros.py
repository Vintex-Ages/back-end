"""Filtro por atributo objetivo na busca conversacional (back-end#260).

Filtro rígido corta, similaridade ordena. A rota compara vetores, então os
testes de rota rodam contra Postgres (`pg_client`). A leitura da pergunta
(`search_interpretation`) e o provedor do Google rodam sem banco, com um
cliente dublê no lugar do SDK.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.catalog import CATEGORIES, COLORS, CONDITIONS, SIZES
from app.constants.embedding import EMBEDDING_DIM
from app.controllers import assistant_controller
from app.controllers.assistant_controller import (
    _aviso_de_alternativas,
    _filtros_da_pergunta,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from app.schemas.product_schema import ProductFilters
from app.services.ai import google as google_mod
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    AIProviderUnavailableError,
    ChatTurn,
    InterpretedQuery,
    SearchDone,
)
from app.services.ai.search_interpretation import (
    INTERPRET_SEARCH_PROMPT,
    InterpretacaoDaPergunta,
    interpretacao_da_resposta,
    montar_pergunta,
)
from app.services.ai.untrusted_text import FIM, INICIO, delimitar

# --- leitura da pergunta ----------------------------------------------------


def test_valor_da_lista_vem_como_o_catalogo_grava() -> None:
    """Caixa e acento diferentes casam com o valor do catálogo, que é o que o
    filtro compara."""
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(
            category="acessorios", color="VERDE", size="m", condition="seminovo"
        )
    )

    assert lida.filters == {
        "category": "Acessórios",
        "color": "Verde",
        "size": "M",
        "condition": "Seminovo",
    }


def test_valor_fora_da_lista_nao_vira_filtro() -> None:
    """Cortaria o catálogo inteiro por um valor que nenhuma peça tem."""
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(category="Tênis", color="Branco e preto", size="XG")
    )

    assert lida.filters == {}


def test_preco_vira_texto_sem_casas_desnecessarias() -> None:
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(price_min=99.9, price_max=400.0)
    )

    assert lida.filters == {"price_min": "99.9", "price_max": "400"}


@pytest.mark.parametrize(
    ("minimo", "maximo"),
    [
        (500.0, 100.0),
        (-10.0, None),
        (None, -1.0),
        (float("nan"), None),
        (None, float("nan")),
        (None, float("inf")),
    ],
)
def test_faixa_de_preco_impossivel_nao_vira_filtro(
    minimo: float | None, maximo: float | None
) -> None:
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(price_min=minimo, price_max=maximo)
    )

    assert "price_min" not in lida.filters
    assert "price_max" not in lida.filters


def test_marca_e_similaridade_passam_limpas() -> None:
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(brand="  Nike ", similarity="  de corrida  ")
    )

    assert lida.filters == {"brand": "Nike"}
    assert lida.similarity == "de corrida"


def test_pergunta_sem_atributo_objetivo_nao_tem_filtro() -> None:
    lida = interpretacao_da_resposta(
        InterpretacaoDaPergunta(similarity="algo confortável para o dia a dia")
    )

    assert lida.filters == {}
    assert lida.similarity == "algo confortável para o dia a dia"


def test_similaridade_vazia_vira_nula() -> None:
    assert (
        interpretacao_da_resposta(InterpretacaoDaPergunta(similarity=" ")).similarity
        is None
    )


@pytest.mark.parametrize(
    "valores", [CATEGORIES, COLORS, CONDITIONS, SIZES], ids=lambda v: v[0]
)
def test_prompt_cita_o_vocabulario_do_catalogo(valores: tuple[str, ...]) -> None:
    for valor in valores:
        assert valor in INTERPRET_SEARCH_PROMPT


def test_pergunta_leva_so_a_conversa_recente_e_cortada() -> None:
    historico = [ChatTurn(role="user", text=f"pergunta {i}") for i in range(10)]
    historico.append(ChatTurn(role="assistant", text="x" * 2000))

    texto = montar_pergunta("e em azul?", historico)

    assert "pergunta 4" not in texto
    assert "pergunta 9" in texto
    assert "Vintex: " + "x" * 500 + "\n" in texto
    assert texto.startswith(INICIO + "\n")
    assert texto.endswith("Pergunta atual: e em azul?\n" + FIM)


# --- provedor do Google -----------------------------------------------------


class _Erro(Exception):
    def __init__(self, code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.code = code


class _Resposta:
    def __init__(self, parsed: Any = None, text: str | None = None) -> None:
        self.parsed = parsed
        self.text = text


class _Modelos:
    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.chamadas.append({"model": model, "contents": contents, "config": config})
        resposta = self.respostas[model]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _google(monkeypatch, respostas: dict[str, Any]) -> tuple:
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "chave-de-teste")
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", ",".join(respostas))
    provider = google_mod.GoogleAIProvider()
    modelos = _Modelos(respostas)
    provider._client = type("C", (), {"models": modelos})()
    return provider, modelos


def _eventos(provider: AIProvider, query: str, history=()) -> list:
    async def coletar() -> list:
        return [e async for e in provider.stream_interpret_search(query, history)]

    return asyncio.run(coletar())


def test_google_interpreta_com_saida_estruturada(monkeypatch) -> None:
    provider, modelos = _google(
        monkeypatch,
        {
            "modelo": _Resposta(
                InterpretacaoDaPergunta(
                    category="Sapatos", color="Verde", price_max=400, similarity=None
                )
            )
        },
    )

    eventos = _eventos(provider, "tênis verde até 400")

    assert eventos == [
        InterpretedQuery(
            filters={"category": "Sapatos", "color": "Verde", "price_max": "400"}
        ),
        SearchDone(),
    ]
    config = modelos.chamadas[0]["config"]
    assert config.response_schema is InterpretacaoDaPergunta
    textos = [p.text for p in modelos.chamadas[0]["contents"][0].parts]
    assert textos == [
        INTERPRET_SEARCH_PROMPT,
        delimitar("Pergunta atual: tênis verde até 400"),
    ]


def test_google_aceita_a_resposta_em_texto(monkeypatch) -> None:
    provider, _ = _google(
        monkeypatch,
        {"modelo": _Resposta(text='{"color": "Preto", "similarity": "festa"}')},
    )

    assert _eventos(provider, "algo preto pra festa")[0] == InterpretedQuery(
        filters={"color": "Preto"}, similarity="festa"
    )


def test_google_429_tenta_o_proximo_modelo(monkeypatch) -> None:
    provider, modelos = _google(
        monkeypatch,
        {
            "primeiro": _Erro(429, "RESOURCE_EXHAUSTED"),
            "segundo": _Resposta(InterpretacaoDaPergunta(size="42")),
        },
    )

    assert _eventos(provider, "tênis 42")[0].filters == {"size": "42"}
    assert [c["model"] for c in modelos.chamadas] == ["primeiro", "segundo"]


@pytest.mark.parametrize(
    "resposta",
    [_Erro(503, "UNAVAILABLE"), _Resposta(text="isto não é json"), _Resposta()],
    ids=["indisponivel", "texto-invalido", "vazia"],
)
def test_google_falha_vira_erro_de_provedor(monkeypatch, resposta: Any) -> None:
    provider, _ = _google(monkeypatch, {"modelo": resposta})

    with pytest.raises(AIProviderError):
        _eventos(provider, "qualquer")


# --- controller -------------------------------------------------------------


def test_filtro_fora_da_lista_da_260_nao_entra() -> None:
    """Loja e localização são filtro do catálogo, mas não da conversa."""
    filtros = _filtros_da_pergunta(
        InterpretedQuery(
            filters={"color": "Verde", "city": "Porto Alegre", "store_id": "3"}
        )
    )

    assert filtros.applied() == {"color": "Verde"}


def test_filtro_invalido_e_ignorado_inteiro() -> None:
    """Vale para qualquer provedor, não só o do Google, que já filtra antes."""
    filtros = _filtros_da_pergunta(
        InterpretedQuery(filters={"price_min": "500", "price_max": "100"})
    )

    assert filtros.applied() == {}


def test_aviso_de_alternativas_diz_o_que_faltou() -> None:
    aviso = _aviso_de_alternativas(
        ProductFilters(category="Sapatos", color="Verde", price_max=Decimal("1400"))
    )

    assert aviso == (
        "Não encontrei peças com Sapatos, Verde e até R$ 1.400,00. Estas são "
        "alternativas, as mais parecidas com o que você pediu."
    )


# --- rota -------------------------------------------------------------------


def _vetor(*pesos: float) -> list[float]:
    vetor = [0.0] * EMBEDDING_DIM
    for indice, peso in enumerate(pesos):
        vetor[indice] = peso
    return vetor


class _Provedor(AIProvider):
    """Interpreta como mandado e devolve o mesmo vetor para qualquer texto."""

    def __init__(self, interpretacao: InterpretedQuery | Exception, vetor) -> None:
        self.interpretacao = interpretacao
        self.vetor = vetor
        self.historicos: list[list[ChatTurn]] = []
        self.textos_do_vetor: list[str] = []

    def analyze_image(self, image_urls):  # noqa: ANN001, ANN201
        raise NotImplementedError

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        self.historicos.append(list(history))
        if isinstance(self.interpretacao, Exception):
            raise self.interpretacao
        yield self.interpretacao
        yield SearchDone()

    def embed(self, texts):  # noqa: ANN001, ANN201
        self.textos_do_vetor.extend(texts)
        return [self.vetor for _ in texts]


def _usar(monkeypatch, provedor: _Provedor) -> _Provedor:
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: provedor)
    return provedor


def _loja(pg_session: Session) -> Store:
    user = User(name="Dona", email="dona@test.local", password_hash="x")
    store = Store(
        name="Brechó",
        seller=Seller(user=user, document_type="CPF", document_value="12345678901"),
    )
    pg_session.add(store)
    pg_session.flush()
    return store


def _peca(pg_session: Session, store: Store, nome: str, vetor, **atributos) -> Product:
    atributos.setdefault("price", Decimal("300"))
    peca = Product(
        store=store,
        name=nome,
        status="ativo",
        embedding=vetor,
        embedding_model=settings.GOOGLE_EMBEDDING_MODEL,
        **atributos,
    )
    pg_session.add(peca)
    pg_session.flush()
    return peca


def _perguntar(client: TestClient, *textos: str) -> list[dict]:
    mensagens = [
        {"role": "user" if i % 2 == 0 else "assistant", "text": t}
        for i, t in enumerate(textos)
    ]
    resposta = client.post("/api/ai/chat", json={"messages": mensagens})
    assert resposta.status_code == 200
    return [
        json.loads(parte[len("data: ") :])
        for parte in resposta.text.strip().split("\n\n")
        if parte.startswith("data: ")
    ]


def _ids(eventos: list[dict]) -> list[int]:
    return [p["id"] for e in eventos if e["type"] == "products" for p in e["products"]]


@pytest.mark.postgres
def test_tenis_verde_ate_400_nao_traz_outra_cor_nem_outro_preco(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """O critério do card: as três mais parecidas estão fora do pedido, e não
    vêm. Pela similaridade sozinha, elas viriam primeiro."""
    loja = _loja(pg_session)
    branco = _peca(
        pg_session, loja, "Tênis branco", _vetor(1), category="Sapatos", color="Branco"
    )
    caro = _peca(
        pg_session,
        loja,
        "Tênis verde caro",
        _vetor(1, 0.1),
        category="Sapatos",
        color="Verde",
        price=Decimal("600"),
    )
    roupa = _peca(
        pg_session,
        loja,
        "Moletom verde",
        _vetor(1, 0.2),
        category="Roupas",
        color="Verde",
    )
    certo = _peca(
        pg_session, loja, "Tênis verde", _vetor(0, 1), category="Sapatos", color="Verde"
    )
    pg_session.commit()
    pedido = {"category": "Sapatos", "color": "Verde", "price_max": "400"}
    _usar(monkeypatch, _Provedor(InterpretedQuery(filters=pedido), _vetor(1)))

    eventos = _perguntar(pg_client, "tênis verde até 400")

    assert eventos[0] == {"type": "interpreted", "filters": pedido, "similarity": None}
    assert _ids(eventos) == [certo.id]
    assert {branco.id, caro.id, roupa.id}.isdisjoint(_ids(eventos))
    assert eventos[1]["match_type"] == "exact"
    assert eventos[-1] == {"type": "done"}


@pytest.mark.postgres
def test_dois_atributos_cortam_e_a_similaridade_ordena_o_resto(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    loja = _loja(pg_session)
    longe = _peca(
        pg_session,
        loja,
        "Vestido preto básico",
        _vetor(0, 1),
        category="Roupas",
        color="Preto",
    )
    perto = _peca(
        pg_session,
        loja,
        "Vestido preto de festa",
        _vetor(1, 0.2),
        category="Roupas",
        color="Preto",
    )
    _peca(
        pg_session,
        loja,
        "Vestido vermelho de festa",
        _vetor(1),
        category="Roupas",
        color="Vermelho",
    )
    pg_session.commit()
    provedor = _usar(
        monkeypatch,
        _Provedor(
            InterpretedQuery(
                filters={"category": "Roupas", "color": "Preto"},
                similarity="para festa",
            ),
            _vetor(1),
        ),
    )

    eventos = _perguntar(pg_client, "vestido preto para festa")

    assert _ids(eventos) == [perto.id, longe.id]
    # O vetor é o da pergunta inteira, e não só do pedaço subjetivo.
    assert provedor.textos_do_vetor == ["vestido preto para festa"]


@pytest.mark.postgres
def test_pergunta_sem_atributo_objetivo_ordena_so_por_similaridade(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    loja = _loja(pg_session)
    segunda = _peca(
        pg_session, loja, "B", _vetor(1, 1), category="Roupas", color="Azul"
    )
    primeira = _peca(
        pg_session, loja, "A", _vetor(1), category="Sapatos", color="Preto"
    )
    pg_session.commit()
    _usar(monkeypatch, _Provedor(InterpretedQuery(similarity="confortável"), _vetor(1)))

    eventos = _perguntar(pg_client, "algo confortável")

    assert eventos[0] == {
        "type": "interpreted",
        "filters": {},
        "similarity": "confortável",
    }
    assert _ids(eventos) == [primeira.id, segunda.id]
    assert eventos[1]["match_type"] == "exact"


@pytest.mark.postgres
def test_filtro_sem_peca_cai_nas_alternativas_marcadas(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """RN-61: nunca vazio, e a resposta diz que são alternativas."""
    loja = _loja(pg_session)
    segunda = _peca(
        pg_session, loja, "Tênis preto", _vetor(0, 1), category="Sapatos", color="Preto"
    )
    primeira = _peca(
        pg_session, loja, "Tênis branco", _vetor(1), category="Sapatos", color="Branco"
    )
    pg_session.commit()
    _usar(
        monkeypatch,
        _Provedor(
            InterpretedQuery(filters={"category": "Sapatos", "color": "Verde"}),
            _vetor(1),
        ),
    )

    eventos = _perguntar(pg_client, "tênis verde")

    assert [e["type"] for e in eventos] == ["interpreted", "text", "products", "done"]
    assert eventos[1]["delta"].startswith("Não encontrei peças com Sapatos e Verde.")
    assert eventos[2]["match_type"] == "fallback"
    assert _ids(eventos) == [primeira.id, segunda.id]


@pytest.mark.postgres
def test_alternativa_mantem_a_categoria_antes_de_soltar_tudo(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """ "bota bege" sem sapato bege: botas de outra cor antes da jaqueta bege,
    mesmo com a jaqueta mais perto no espaço vetorial."""
    loja = _loja(pg_session)
    jaqueta = _peca(
        pg_session, loja, "Jaqueta bege", _vetor(1), category="Roupas", color="Bege"
    )
    bota = _peca(
        pg_session,
        loja,
        "Bota branca",
        _vetor(0, 1),
        category="Sapatos",
        color="Branco",
    )
    pg_session.commit()
    _usar(
        monkeypatch,
        _Provedor(
            InterpretedQuery(filters={"category": "Sapatos", "color": "Bege"}),
            _vetor(1),
        ),
    )

    eventos = _perguntar(pg_client, "bota bege")

    assert _ids(eventos) == [bota.id]
    assert jaqueta.id not in _ids(eventos)
    assert eventos[2]["match_type"] == "fallback"


@pytest.mark.postgres
def test_categoria_sem_peca_solta_todos_os_filtros(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    loja = _loja(pg_session)
    jaqueta = _peca(
        pg_session, loja, "Jaqueta bege", _vetor(1), category="Roupas", color="Bege"
    )
    pg_session.commit()
    _usar(
        monkeypatch,
        _Provedor(
            InterpretedQuery(filters={"category": "Sapatos", "color": "Bege"}),
            _vetor(1),
        ),
    )

    eventos = _perguntar(pg_client, "bota bege")

    assert _ids(eventos) == [jaqueta.id]
    assert eventos[2]["match_type"] == "fallback"


@pytest.mark.postgres
def test_falha_na_interpretacao_busca_so_por_similaridade(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """A interpretação ajuda, mas não trava a conversa (RN-57)."""
    loja = _loja(pg_session)
    peca = _peca(
        pg_session, loja, "Tênis branco", _vetor(1), category="Sapatos", color="Branco"
    )
    pg_session.commit()
    _usar(monkeypatch, _Provedor(AIProviderUnavailableError("429"), _vetor(1)))

    eventos = _perguntar(pg_client, "tênis verde")

    assert [e["type"] for e in eventos] == ["products", "done"]
    assert _ids(eventos) == [peca.id]
    assert eventos[0]["match_type"] == "exact"


@pytest.mark.postgres
def test_interpretacao_recebe_a_conversa_anterior(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    provedor = _usar(monkeypatch, _Provedor(InterpretedQuery(), _vetor(1)))

    _perguntar(pg_client, "tênis de corrida", "Achei estes.", "e em azul?")

    assert provedor.historicos == [
        [
            ChatTurn(role="user", text="tênis de corrida"),
            ChatTurn(role="assistant", text="Achei estes."),
        ]
    ]
