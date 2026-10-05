"""O prompt da analise de foto cita o vocabulario fechado do catalogo.

Sem isso o modelo responde texto livre e o formulario descarta: ele respondia
"Camiseta" para categoria (que e tipo de peca, nao familia do catalogo) e
"Branco e preto" para cor, e nenhum dos dois existe nas opcoes da tela.
Medido na primeira execucao com a API real: 2 de 6 campos aproveitados.
"""

from __future__ import annotations

import pytest

from app.constants.catalog import CATEGORIES, COLORS, CONDITIONS, SIZES
from app.seeds import pecas as seed_pecas
from app.services.ai.google import _ANALYZE_IMAGE_PROMPT


@pytest.mark.parametrize(
    ("campo", "valores"),
    [
        ("category", CATEGORIES),
        ("color", COLORS),
        ("condition", CONDITIONS),
        ("size", SIZES),
    ],
)
def test_prompt_cita_todos_os_valores_de_cada_lista(
    campo: str, valores: tuple[str, ...]
) -> None:
    assert campo in _ANALYZE_IMAGE_PROMPT
    for valor in valores:
        assert valor in _ANALYZE_IMAGE_PROMPT, f"{campo}: falta '{valor}' no prompt"


def test_prompt_manda_usar_o_valor_exato() -> None:
    """Sem esta instrucao o modelo devolve sinonimo ou minuscula, e o
    formulario descarta do mesmo jeito."""
    assert "valor exato" in _ANALYZE_IMAGE_PROMPT


def test_prompt_manda_deixar_nulo_quando_nada_serve() -> None:
    """Valor aproximado e pior que vazio: o vendedor corrige campo vazio, mas
    nao percebe um valor errado ja preenchido."""
    assert "deixe o campo nulo" in _ANALYZE_IMAGE_PROMPT.lower()


def test_prompt_nao_pede_para_estimar_tamanho_pelo_caimento() -> None:
    """Tamanho so sai de etiqueta legivel. Estimar pelo caimento enche o campo
    com chute que o vendedor nao revisa."""
    assert "Não estime pelo caimento" in _ANALYZE_IMAGE_PROMPT


def test_prompt_segue_sem_chutar_marca() -> None:
    """RN-58, que ja valia antes desta mudanca."""
    assert "Nunca chute a marca" in _ANALYZE_IMAGE_PROMPT


def test_seed_usa_o_mesmo_vocabulario_do_prompt() -> None:
    """Duas copias da lista divergem. O seed grava o que os filtros comparam,
    entao tem que ser a mesma fonte que o prompt cita."""
    assert tuple(seed_pecas.COLORS) == COLORS
    assert tuple(seed_pecas.CONDITIONS) == CONDITIONS
    assert set(seed_pecas.TIPOS) == set(CATEGORIES)
