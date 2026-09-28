"""Vocabulário fechado dos atributos da peça.

Estes são os valores que o catálogo realmente guarda em `products.*` e que os
filtros comparam por igualdade. Quem escreve num desses campos — o seed, o
formulário de cadastro, a sugestão da IA — tem que usar exatamente estes
valores, senão a peça existe mas não é encontrada pelo filtro.

Estava só dentro de `app/seeds/pecas.py`, onde nada além do seed enxergava.
A sugestão da IA (`back-end#150`) respondia texto livre por isso: o prompt
pedia "tipo da peça" e devolvia "Camiseta", que não é categoria nenhuma do
catálogo, e "Branco e preto", que não é cor nenhuma. O vendedor via o aviso de
que a IA leu algo fora da lista e tinha que escolher à mão.
"""

from __future__ import annotations

CATEGORIES: tuple[str, ...] = ("Roupas", "Sapatos", "Acessórios")

COLORS: tuple[str, ...] = (
    "Preto",
    "Branco",
    "Bege",
    "Vermelho",
    "Azul",
    "Verde",
    "Estampado",
)

CONDITIONS: tuple[str, ...] = (
    "Novo com etiqueta",
    "Seminovo",
    "Usado",
    "Marcas de uso",
)

# Numeração para calçado e letra para o resto; a peça usa uma faixa ou a outra
# conforme a categoria, e o modelo escolhe pelo que enxerga na foto.
SIZES: tuple[str, ...] = ("PP", "P", "M", "G", "GG", "36", "38", "40", "42")


def lista(valores: tuple[str, ...]) -> str:
    """Valores separados por vírgula, para citar dentro de um prompt."""
    return ", ".join(valores)
