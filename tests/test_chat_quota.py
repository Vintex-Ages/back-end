"""Cota da busca conversacional (back-end#258).

A rota do chat compara vetores, e isso só o Postgres faz: os testes de rota
rodam contra `pg_client`. A regra da cota em si (somar, recusar, desfazer) não
depende de vetor e roda também no SQLite, que é o outro dialeto do repositório.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.controllers import assistant_controller
from app.models.ai_chat_usage import AIChatUsage
from app.models.user import User
from app.repositories.ai_chat_usage_repository import AIChatUsageRepository
from app.services import chat_quota
from app.services.ai.base import (
    AIProvider,
    AIProviderUnavailableError,
    ImageAnalysisResult,
)
from app.services.chat_quota import CHAVE_DO_PROJETO, ChatQuota, CotaEsgotada

# 15h UTC de 25/10: a cota volta à meia-noite UTC, 21h de Brasília.
_AGORA = datetime(2026, 10, 25, 15, 0)
_DIA = _AGORA.date()


class _Provider(AIProvider):
    """Conta as chamadas: pergunta recusada pela cota não chega ao provedor."""

    def __init__(self) -> None:
        self.embeds = 0
        self.analises = 0

    def analyze_image(self, image_urls):  # noqa: ANN001, ANN201
        self.analises += 1
        return ImageAnalysisResult()

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        raise AIProviderUnavailableError("sem interpretação")
        yield  # pragma: no cover

    def embed(self, texts):  # noqa: ANN001, ANN201
        self.embeds += 1
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]


@pytest.fixture
def provider(monkeypatch) -> _Provider:
    p = _Provider()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: p)
    monkeypatch.setattr(chat_quota, "utcnow_naive", lambda: _AGORA)
    return p


def _cotas(monkeypatch, por_pessoa: int, por_dia: int) -> None:
    monkeypatch.setattr(settings, "CHAT_QUOTA_PER_PERSON", por_pessoa)
    monkeypatch.setattr(settings, "CHAT_QUOTA_PER_DAY", por_dia)


def _perguntar(client: TestClient, headers: dict[str, str] | None = None) -> list:
    resposta = client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "user", "text": "jaqueta jeans"}]},
        headers=headers or {},
    )
    assert resposta.status_code == 200
    return [
        json.loads(parte[len("data: ") :])
        for parte in resposta.text.strip().split("\n\n")
        if parte.startswith("data: ")
    ]


def _usuario(pg_session: Session, nome: str) -> User:
    user = User(name=nome, email=f"{nome}@test.local", password_hash="x")
    pg_session.add(user)
    pg_session.commit()
    return user


# --- rota ------------------------------------------------------------------


@pytest.mark.postgres
def test_estourar_a_cota_por_pessoa(
    pg_client: TestClient, provider: _Provider, monkeypatch
) -> None:
    _cotas(monkeypatch, por_pessoa=2, por_dia=40)

    assert _perguntar(pg_client)[0]["type"] == "products"
    assert _perguntar(pg_client)[0]["type"] == "products"
    eventos = _perguntar(pg_client)

    assert eventos == [
        {
            "type": "error",
            "code": "quota_exceeded",
            "message": (
                "Você atingiu o limite de 2 perguntas por dia à Vintex. Volta a "
                "funcionar em 25/10 às 21h (horário de Brasília)."
            ),
            "retry_at": "2026-10-26T00:00:00Z",
        },
        {"type": "done"},
    ]
    # A terceira não gastou requisição do provedor.
    assert provider.embeds == 2


@pytest.mark.postgres
def test_estourar_a_cota_do_projeto(
    pg_client: TestClient,
    pg_session: Session,
    provider: _Provider,
    auth_headers,
    monkeypatch,
) -> None:
    _cotas(monkeypatch, por_pessoa=5, por_dia=2)
    ana = auth_headers(_usuario(pg_session, "ana").id)
    bia = _usuario(pg_session, "bia")

    _perguntar(pg_client, ana)
    _perguntar(pg_client, ana)
    eventos = _perguntar(pg_client, auth_headers(bia.id))

    assert eventos[0]["code"] == "quota_exceeded"
    assert eventos[0]["message"].startswith(
        "A Vintex atingiu o limite de perguntas do dia para todo mundo."
    )
    assert eventos[-1] == {"type": "done"}
    assert provider.embeds == 2
    # Recusada pelo projeto, a pergunta da Bia também não conta para ela.
    uso = AIChatUsageRepository(pg_session)
    assert uso.contagem(_DIA, f"user:{bia.id}") == 0
    assert uso.contagem(_DIA, CHAVE_DO_PROJETO) == 2


@pytest.mark.postgres
def test_logada_conta_pelo_id_e_visitante_pela_origem(
    pg_client: TestClient,
    pg_session: Session,
    provider: _Provider,
    auth_headers,
    monkeypatch,
) -> None:
    """Sem login o chat continua funcionando (RN-65), dentro da própria cota."""
    _cotas(monkeypatch, por_pessoa=1, por_dia=40)
    ana = _usuario(pg_session, "ana")

    assert _perguntar(pg_client, auth_headers(ana.id))[0]["type"] == "products"
    assert _perguntar(pg_client, auth_headers(ana.id))[0]["type"] == "error"
    # Mesma máquina, sem sessão: é outra pessoa para a cota.
    assert _perguntar(pg_client)[0]["type"] == "products"
    assert _perguntar(pg_client)[0]["type"] == "error"

    uso = AIChatUsageRepository(pg_session)
    assert uso.contagem(_DIA, f"user:{ana.id}") == 1
    assert uso.contagem(_DIA, "ip:testclient") == 1


@pytest.mark.postgres
def test_token_invalido_no_chat_conta_como_visitante(
    pg_client: TestClient, pg_session: Session, provider: _Provider
) -> None:
    eventos = _perguntar(pg_client, {"Authorization": "Bearer nao-e-um-token"})

    assert eventos[0]["type"] == "products"
    assert AIChatUsageRepository(pg_session).contagem(_DIA, "ip:testclient") == 1


@pytest.mark.postgres
def test_provedor_desligado_nao_gasta_a_cota(
    pg_client: TestClient, pg_session: Session, monkeypatch
) -> None:
    """Nada chegaria ao provedor: gastar a pergunta só puniria a pessoa."""

    def _desligado() -> AIProvider:
        raise AIProviderUnavailableError("AI_PROVIDER=unavailable")

    monkeypatch.setattr(assistant_controller, "get_ai_provider", _desligado)
    monkeypatch.setattr(chat_quota, "utcnow_naive", lambda: _AGORA)

    assert [e["type"] for e in _perguntar(pg_client)] == ["error", "done"]
    assert AIChatUsageRepository(pg_session).contagem(_DIA, CHAVE_DO_PROJETO) == 0


@pytest.mark.postgres
def test_cota_esgotada_nao_trava_a_sugestao_de_anuncio(
    pg_client: TestClient,
    pg_session: Session,
    provider: _Provider,
    auth_headers,
    monkeypatch,
) -> None:
    """O cadastro de peça não divide a cota do chat, e continua exigindo login."""
    _cotas(monkeypatch, por_pessoa=1, por_dia=1)
    ana = auth_headers(_usuario(pg_session, "ana").id)
    _perguntar(pg_client, ana)
    assert _perguntar(pg_client, ana)[0]["code"] == "quota_exceeded"

    corpo = {"image_urls": ["https://cdn.test/foto.jpg"]}
    assert pg_client.post("/api/ai/listing-suggestions", json=corpo).status_code == 401
    resposta = pg_client.post("/api/ai/listing-suggestions", json=corpo, headers=ana)

    assert resposta.status_code == 200
    assert provider.analises == 1


# --- regra -----------------------------------------------------------------


def test_recusa_pela_cota_do_projeto_nao_conta_para_a_pessoa(
    db_session: Session, monkeypatch
) -> None:
    _cotas(monkeypatch, por_pessoa=5, por_dia=1)
    quota = ChatQuota(db_session)
    quota.reservar("user:1", _AGORA)

    with pytest.raises(CotaEsgotada) as recusa:
        quota.reservar("user:2", _AGORA)

    assert recusa.value.escopo == "projeto"
    uso = AIChatUsageRepository(db_session)
    assert uso.contagem(_DIA, "user:1") == 1
    assert uso.contagem(_DIA, "user:2") == 0
    assert uso.contagem(_DIA, CHAVE_DO_PROJETO) == 1


def test_a_cota_volta_no_dia_seguinte(db_session: Session, monkeypatch) -> None:
    _cotas(monkeypatch, por_pessoa=1, por_dia=40)
    quota = ChatQuota(db_session)
    quota.reservar("ip:1.2.3.4", _AGORA)
    with pytest.raises(CotaEsgotada):
        quota.reservar("ip:1.2.3.4", _AGORA)

    quota.reservar("ip:1.2.3.4", datetime(2026, 10, 26, 0, 0))

    assert AIChatUsageRepository(db_session).contagem(date(2026, 10, 26), "ip:1.2.3.4")


def test_configuracao_recusa_cota_zero() -> None:
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(CHAT_QUOTA_PER_PERSON=0)


@pytest.mark.postgres
def test_duas_perguntas_ao_mesmo_tempo_na_ultima_vaga(pg_engine: Engine) -> None:
    """Conferir e somar é um comando só: das duas, só uma leva a vaga.

    Conexões de verdade, cada uma com seu commit, para as duas transações
    disputarem a mesma linha como em produção. Dia fora do calendário do resto
    da suíte, apagado no fim.
    """
    dia = date(2000, 1, 1)
    largada = threading.Barrier(2)
    somou: list[bool] = []

    def perguntar() -> None:
        with Session(pg_engine) as s:
            largada.wait()
            somou.append(AIChatUsageRepository(s).consumir(dia, "user:corrida", 1))
            s.commit()

    try:
        threads = [threading.Thread(target=perguntar) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(somou) == [False, True]
        with Session(pg_engine) as s:
            assert AIChatUsageRepository(s).contagem(dia, "user:corrida") == 1
    finally:
        with Session(pg_engine) as s:
            s.execute(delete(AIChatUsage).where(AIChatUsage.day == dia))
            s.commit()
