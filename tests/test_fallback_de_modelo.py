"""503 num modelo faz tentar o proximo da lista (back-end#209).

Medido em 27/09 com a API real: 4 falhas em 5 chamadas num intervalo de vinte
minutos, com seis outros modelos respondendo no mesmo periodo. A capacidade
oscila por modelo, entao depender de um nome unico deixa a funcionalidade
central da sprint sujeita a uma moeda.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import settings
from app.services.ai import google as mod
from app.services.ai.base import AIProviderError, ImageAnalysisResult


class _Erro(Exception):
    """Erro do SDK, que expoe o codigo em `.code`."""

    def __init__(self, code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.code = code


class _Modelos:
    """Dubla `client.models`, respondendo por modelo."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamados: list[str] = []

    def generate_content(self, *, model: str, **_: Any) -> Any:  # noqa: ANN401
        self.chamados.append(model)
        r = self.respostas[model]
        if isinstance(r, Exception):
            raise r
        return r


class _Resposta:
    def __init__(self, parsed: ImageAnalysisResult) -> None:
        self.parsed = parsed
        self.text = None


def _provider(monkeypatch, modelos: str, respostas: dict[str, Any]) -> tuple:
    """Exercita `_gerar_com_fallback` direto.

    O download das fotos e inline no `analyze_image`, entao chamar por la
    exigiria rede. A escolha de modelo, que e o que este arquivo cobre, mora
    no metodo abaixo e nao depende das imagens.
    """
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", modelos)
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "chave-de-teste")

    p = mod.GoogleAIProvider()
    duble = _Modelos(respostas)
    p._client = type("C", (), {"models": duble})()
    return p, duble


def test_lista_com_um_nome_so_continua_funcionando(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", "gemini-3.8-flash")
    assert mod.modelos_de_visao() == ["gemini-3.8-flash"]


def test_lista_separada_por_virgula_vira_lista(monkeypatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", " a , b ,, c ")
    assert mod.modelos_de_visao() == ["a", "b", "c"]


@pytest.mark.parametrize(
    ("exc", "esperado"),
    [
        (_Erro(503, "UNAVAILABLE"), True),
        (Exception("503 UNAVAILABLE. high demand"), True),
        (_Erro(404, "NOT_FOUND"), False),
        (_Erro(400, "INVALID_ARGUMENT"), False),
        (Exception("qualquer outra coisa"), False),
    ],
)
def test_reconhece_indisponibilidade(exc: Exception, esperado: bool) -> None:
    assert mod._e_indisponibilidade(exc) is esperado


def test_503_no_primeiro_usa_o_segundo(monkeypatch) -> None:
    esperado = ImageAnalysisResult()
    p, duble = _provider(
        monkeypatch,
        "primeiro,segundo",
        {
            "primeiro": _Erro(503, "UNAVAILABLE. high demand"),
            "segundo": _Resposta(esperado),
        },
    )

    assert p._gerar_com_fallback([]).parsed == esperado
    assert duble.chamados == ["primeiro", "segundo"]


def test_404_no_primeiro_nao_tenta_o_segundo(monkeypatch) -> None:
    """Nome que nao existe para a chave e erro de configuracao. Tentar outro
    esconderia a causa e o time perseguiria o sintoma errado."""
    p, duble = _provider(
        monkeypatch,
        "primeiro,segundo",
        {
            "primeiro": _Erro(404, "NOT_FOUND"),
            "segundo": _Resposta(ImageAnalysisResult()),
        },
    )

    with pytest.raises(AIProviderError):
        p._gerar_com_fallback([])

    assert duble.chamados == ["primeiro"]


def test_todos_indisponiveis_levanta_erro_de_provedor(monkeypatch) -> None:
    p, duble = _provider(
        monkeypatch,
        "a,b,c",
        {n: _Erro(503, "UNAVAILABLE") for n in ("a", "b", "c")},
    )

    with pytest.raises(AIProviderError, match="Falha ao analisar"):
        p._gerar_com_fallback([])

    assert duble.chamados == ["a", "b", "c"]
