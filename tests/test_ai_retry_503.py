"""Rodadas da cadeia de modelos quando todos respondem 503 (back-end#264)."""

from __future__ import annotations

import pytest

from app.services.ai import google as mod
from app.services.ai.base import AIProviderError


class _Erro503(Exception):
    code = 503

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "503 UNAVAILABLE. high demand"


class _Erro400(Exception):
    code = 400

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "400 INVALID_ARGUMENT"


def _provider(monkeypatch, respostas, modelos=("a", "b", "c")):
    """GoogleAIProvider com `generate_content` roteirizado, sem rede nem espera."""
    monkeypatch.setattr(mod, "modelos_de_visao", lambda: list(modelos))
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    chamadas: list[str] = []

    def generate_content(model, **_kw):
        chamadas.append(model)
        atual = respostas.pop(0)
        if isinstance(atual, Exception):
            raise atual
        return atual

    p = mod.GoogleAIProvider.__new__(mod.GoogleAIProvider)
    p._client = type(
        "C",
        (),
        {
            "models": type(
                "M", (), {"generate_content": staticmethod(generate_content)}
            )()
        },
    )()
    return p, chamadas


def test_repete_a_cadeia_quando_todos_dao_503(monkeypatch):
    """Primeira rodada toda em 503, segunda responde: devolve sem levantar."""
    respostas = [_Erro503(), _Erro503(), _Erro503(), "ok"]
    p, chamadas = _provider(monkeypatch, respostas)

    assert p._gerar_com_fallback([]) == "ok"
    assert chamadas == ["a", "b", "c", "a"], "tem que recomeçar pelo primeiro modelo"


def test_desiste_depois_das_rodadas(monkeypatch):
    """Todas as rodadas em 503: levanta a mensagem de sempre."""
    respostas = [_Erro503()] * (3 * mod._RODADAS)
    p, chamadas = _provider(monkeypatch, respostas)

    with pytest.raises(AIProviderError, match="Falha ao analisar as fotos"):
        p._gerar_com_fallback([])
    assert len(chamadas) == 3 * mod._RODADAS


def test_erro_que_nao_e_503_levanta_na_hora(monkeypatch):
    """400 é erro nosso: não tenta outro modelo nem espera."""
    respostas = [_Erro400(), "nunca chega aqui"]
    p, chamadas = _provider(monkeypatch, respostas)

    with pytest.raises(AIProviderError):
        p._gerar_com_fallback([])
    assert chamadas == ["a"], "não pode tentar o segundo modelo"
