"""Registro de cada chamada ao provedor de IA e o consumo do dia (back-end#263).

O provedor é o do Google com o cliente dublado, como em
`test_fallback_de_modelo.py`: o que se testa é o que o provedor grava em cada
tentativa, não a resposta do modelo.

Cada teste roda as chamadas num `Context()` vazio. `definir_funcionalidade` não
desfaz o valor (o contexto de uma requisição morre com ela), e sem isso o valor
de um teste vazaria para o seguinte, que roda na mesma thread.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import Context
from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.controllers import assistant_controller
from app.controllers.assistant_controller import AssistantController
from app.models.ai_call_log import AICallLog
from app.models.user import User
from app.repositories.ai_call_log_repository import AICallLogRepository
from app.services.ai import google as mod
from app.services.ai import registro
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    ChatTurn,
    ImageAnalysisResult,
)
from app.services.ai.registro import definir_funcionalidade, funcionalidade_atual

_PERGUNTA = "jaqueta jeans azul pra usar no inverno"


class _Erro(Exception):
    """Erro do SDK, que expõe o código em `.code`."""

    def __init__(self, code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.code = code


class _Resposta:
    def __init__(self) -> None:
        self.parsed = ImageAnalysisResult()
        self.text = None


class _Embedding:
    def __init__(self) -> None:
        self.values = [0.1] * mod.EMBEDDING_DIM


class _Modelos:
    """Dubla `client.models`, respondendo por modelo."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas

    def generate_content(self, *, model: str, **_: Any) -> Any:  # noqa: ANN401
        r = self.respostas[model]
        if isinstance(r, Exception):
            raise r
        return r

    def embed_content(self, *, model: str, **_: Any) -> Any:  # noqa: ANN401
        r = self.respostas[model]
        if isinstance(r, Exception):
            raise r
        return type("R", (), {"embeddings": [_Embedding()]})()


@pytest.fixture
def registro_no_banco_de_teste(monkeypatch, db_session):
    """O registro grava no mesmo banco do teste, e não no `SessionLocal`."""
    monkeypatch.setattr(
        registro, "session_factory", sessionmaker(bind=db_session.get_bind())
    )
    return db_session


def _provider(monkeypatch, respostas: dict[str, Any], modelos: str = "") -> Any:
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "chave-de-teste")
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", modelos or "visao")
    monkeypatch.setattr(settings, "GOOGLE_EMBEDDING_MODEL", "vetor-1")
    p = mod.GoogleAIProvider()
    p._client = type("C", (), {"models": _Modelos(respostas)})()
    return p


def _em_contexto_novo(
    funcionalidade: str | None, chamada, *args
):  # noqa: ANN001, ANN202
    def rodar():  # noqa: ANN202
        if funcionalidade:
            definir_funcionalidade(funcionalidade)
        return chamada(*args)

    return Context().run(rodar)


def _linhas(db) -> list[AICallLog]:  # noqa: ANN001
    db.expire_all()
    return list(db.scalars(select(AICallLog).order_by(AICallLog.id)))


# --- o que cada chamada grava -------------------------------------------------


def test_chamada_com_sucesso_grava_funcionalidade_modelo_duracao_e_resultado(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    p = _provider(monkeypatch, {"visao": _Resposta()})

    _em_contexto_novo("cadastro_foto", p._gerar_com_fallback, [])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert linha.feature == "cadastro_foto"
    assert linha.operation == "gerar"
    assert linha.model == "visao"
    assert linha.success is True
    assert linha.error_code is None
    assert linha.duration_ms >= 0


def test_falha_do_provedor_fica_separada_do_sucesso_com_o_codigo(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    p = _provider(monkeypatch, {"visao": _Erro(400, "INVALID_ARGUMENT")})

    with pytest.raises(AIProviderError):
        _em_contexto_novo("busca_imagem", p._gerar_com_fallback, [])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert (linha.feature, linha.success, linha.error_code) == (
        "busca_imagem",
        False,
        "400",
    )


def test_fallback_registra_a_tentativa_recusada_e_o_modelo_que_respondeu(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    p = _provider(
        monkeypatch,
        {"primeiro": _Erro(503, "UNAVAILABLE"), "segundo": _Resposta()},
        modelos="primeiro,segundo",
    )

    _em_contexto_novo("conversa", p._gerar_com_fallback, [])

    linhas = _linhas(registro_no_banco_de_teste)
    assert [(x.model, x.success, x.error_code) for x in linhas] == [
        ("primeiro", False, "503"),
        ("segundo", True, None),
    ]


def test_vetor_e_registrado_como_operacao_propria(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    p = _provider(monkeypatch, {"vetor-1": None})

    _em_contexto_novo("recomendacao", p.embed, ["perfil boho"])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert (linha.feature, linha.operation, linha.model, linha.success) == (
        "recomendacao",
        "vetor",
        "vetor-1",
        True,
    )


def test_falha_do_vetor_grava_o_codigo(monkeypatch, registro_no_banco_de_teste) -> None:
    p = _provider(monkeypatch, {"vetor-1": _Erro(429, "RESOURCE_EXHAUSTED")})

    with pytest.raises(AIProviderError):
        _em_contexto_novo("conversa", p.embed, [_PERGUNTA])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert (linha.operation, linha.success, linha.error_code) == ("vetor", False, "429")


def test_quem_nao_declara_a_funcionalidade_aparece_como_nao_informada(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    p = _provider(monkeypatch, {"visao": _Resposta()})

    _em_contexto_novo(None, p._gerar_com_fallback, [])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert linha.feature == "nao_informada"


def test_registro_nao_guarda_a_pergunta_nem_a_mensagem_do_erro(
    monkeypatch, registro_no_banco_de_teste
) -> None:
    """Erro sem código vira o nome da exceção: a mensagem pode repetir o que
    foi mandado ao modelo."""
    p = _provider(monkeypatch, {"vetor-1": RuntimeError(f"falhou com {_PERGUNTA}")})

    with pytest.raises(AIProviderError):
        _em_contexto_novo("conversa", p.embed, [_PERGUNTA])

    [linha] = _linhas(registro_no_banco_de_teste)
    assert linha.error_code == "RuntimeError"
    valores = [str(getattr(linha, c.name)) for c in AICallLog.__table__.columns]
    assert not any("jaqueta" in v for v in valores)


def test_falha_ao_registrar_e_logada_e_nao_derruba_a_chamada(
    monkeypatch, caplog
) -> None:
    def banco_fora():  # noqa: ANN202
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(registro, "session_factory", banco_fora)
    p = _provider(monkeypatch, {"visao": _Resposta()})

    with caplog.at_level(logging.ERROR, logger=registro.logger.name):
        resposta = _em_contexto_novo("cadastro_foto", p._gerar_com_fallback, [])

    assert resposta.parsed == ImageAnalysisResult()
    assert "Falha ao registrar chamada de IA" in caplog.text


# --- a funcionalidade chega até o provedor ------------------------------------


class _Espiao(AIProvider):
    """Anota a funcionalidade vista em cada chamada e falha, para o chat parar
    antes da busca por vetor (que só roda no Postgres)."""

    def __init__(self) -> None:
        self.vistas: list[str] = []

    def analyze_image(self, image_urls):  # noqa: ANN001, ANN201
        self.vistas.append(funcionalidade_atual())
        return ImageAnalysisResult()

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        self.vistas.append(await asyncio.to_thread(funcionalidade_atual))
        raise AIProviderError("sem interpretação")
        yield  # pragma: no cover

    def embed(self, texts):  # noqa: ANN001, ANN201
        self.vistas.append(funcionalidade_atual())
        raise AIProviderError("sem vetor")


def test_cadastro_pela_foto_declara_a_funcionalidade(monkeypatch, db_session) -> None:
    espiao = _Espiao()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: espiao)

    _em_contexto_novo(
        None, AssistantController(db_session).suggest_listing, ["https://x/f.jpg"]
    )

    assert espiao.vistas == ["cadastro_foto"]


def test_conversa_declara_a_funcionalidade_ate_dentro_do_threadpool(
    monkeypatch, db_session
) -> None:
    """O chat chama o provedor por `asyncio.to_thread` e `run_in_threadpool`:
    a funcionalidade precisa atravessar os dois."""
    espiao = _Espiao()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: espiao)
    monkeypatch.setattr(assistant_controller, "modelo_de_embedding", lambda: "m")

    async def conversar() -> None:
        mensagens = [ChatTurn(role="user", text=_PERGUNTA)]
        async for _ in AssistantController(db_session).chat(mensagens, "ip:teste"):
            pass

    _em_contexto_novo(None, asyncio.run, conversar())

    assert espiao.vistas == ["conversa", "conversa"]


# --- o consumo do dia ---------------------------------------------------------


def _gravar(db, dia: date, **campos) -> None:  # noqa: ANN001, ANN003
    padrao = {
        "feature": "conversa",
        "operation": "gerar",
        "model": "visao",
        "duration_ms": 120,
        "success": True,
        "error_code": None,
    }
    db.add(
        AICallLog(
            created_at=datetime(dia.year, dia.month, dia.day, 12),
            **{**padrao, **campos},
        )
    )


@pytest.fixture
def admin_headers(db_session, auth_headers) -> dict[str, str]:
    admin = User(
        name="Admin", email="admin@test.local", password_hash="x", is_admin=True
    )
    db_session.add(admin)
    db_session.commit()
    return auth_headers(admin.id, is_admin=True)


def test_le_o_consumo_do_dia_por_funcionalidade_e_por_modelo(
    client, db_session, admin_headers, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER_DAILY_LIMIT", 50)
    dia, ontem = date(2026, 11, 14), date(2026, 11, 13)
    _gravar(db_session, dia, feature="conversa")
    _gravar(db_session, dia, feature="conversa", operation="vetor", model="vetor-1")
    _gravar(db_session, dia, feature="cadastro_foto", success=False, error_code="503")
    _gravar(db_session, dia, feature="cadastro_foto")
    _gravar(db_session, ontem, feature="busca_imagem")
    db_session.commit()

    resposta = client.get(
        "/api/admin/ai-usage", params={"day": "2026-11-14"}, headers=admin_headers
    )

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["day"] == "2026-11-14"
    assert (body["successes"], body["failures"]) == (3, 1)
    assert (body["daily_limit"], body["remaining"]) == (50, 47)
    assert body["by_feature"] == [
        {"name": "cadastro_foto", "successes": 1, "failures": 1},
        {"name": "conversa", "successes": 2, "failures": 0},
    ]
    assert body["by_model"] == [
        {"name": "vetor-1", "successes": 1, "failures": 0},
        {"name": "visao", "successes": 2, "failures": 1},
    ]


def test_restante_nao_fica_negativo(
    client, db_session, admin_headers, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "AI_PROVIDER_DAILY_LIMIT", 1)
    dia = date(2026, 11, 14)
    _gravar(db_session, dia)
    _gravar(db_session, dia)
    db_session.commit()

    body = client.get(
        "/api/admin/ai-usage", params={"day": dia.isoformat()}, headers=admin_headers
    ).json()

    assert body["remaining"] == 0


def test_sem_dia_le_o_de_hoje_em_utc(client, db_session, admin_headers) -> None:
    repo = AICallLogRepository(db_session)
    repo.registrar(
        feature="publicacao",
        operation="vetor",
        model="vetor-1",
        duration_ms=80,
        success=True,
        error_code=None,
    )
    db_session.commit()

    body = client.get("/api/admin/ai-usage", headers=admin_headers).json()

    assert body["by_feature"] == [{"name": "publicacao", "successes": 1, "failures": 0}]


def test_consumo_exige_administradora(client, usuario_sem_loja, auth_headers) -> None:
    assert client.get("/api/admin/ai-usage").status_code == 401
    assert (
        client.get(
            "/api/admin/ai-usage", headers=auth_headers(usuario_sem_loja.id)
        ).status_code
        == 403
    )
