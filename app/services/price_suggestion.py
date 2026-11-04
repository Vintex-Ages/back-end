"""Sugestão de preço a partir do catálogo (BE-US018-1, back-end#254).

**A fonte é o próprio catálogo**, sem consulta externa e sem chamar modelo de
IA. A faixa sai dos preços das peças parecidas, achadas por similaridade
vetorial com os vetores que o catálogo **já tem gravados**:

1. a peça que está sendo cadastrada ainda não tem vetor, e gerar um seria uma
   chamada ao provedor. Então o ponto de partida são as peças do catálogo
   cujo nome mais casa com o nome digitado (`vetores_pelo_nome`);
2. a média dos vetores delas é a posição da peça nova no espaço vetorial;
3. as peças mais próximas dessa posição são as comparáveis
   (`find_similar`), e categoria, conservação, marca e tamanho refinam a
   comparação enquanto sobrar base;
4. a faixa é o miolo da distribuição de preços delas.

Sem base suficiente (`PRICE_SUGGESTION_MIN_BASE`), não inventa número:
`min` e `max` vêm nulos e a justificativa diz por quê. A sugestão alerta e
nunca impede o preço escolhido (RN-68); nada aqui é gravado.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

# Palavras do nome que entram na busca: as primeiras, sem repetição. "de",
# "da", "com" ficam de fora pelo tamanho.
_MAX_PALAVRAS = 8
_MIN_LETRAS = 3


def palavras_do_nome(nome: str) -> list[str]:
    """As palavras que identificam a peça, sem acento e sem caixa, como a
    busca textual do catálogo compara (RN-41)."""
    decomposto = unicodedata.normalize("NFKD", nome.lower())
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    palavras: list[str] = []
    for palavra in re.findall(r"[\w']+", sem_acento):
        if len(palavra) >= _MIN_LETRAS and palavra not in palavras:
            palavras.append(palavra)
    return palavras[:_MAX_PALAVRAS]


def centroide(vetores: Sequence[Sequence[float]]) -> list[float]:
    """A média dos vetores, coordenada a coordenada."""
    quantidade = len(vetores)
    return [float(sum(coluna)) / quantidade for coluna in zip(*vetores)]


def _percentil(ordenados: Sequence[Decimal], fracao: Decimal) -> Decimal:
    """Interpolação linear entre os dois vizinhos, como o `numpy` por padrão."""
    posicao = fracao * (len(ordenados) - 1)
    abaixo = int(posicao)
    acima = min(abaixo + 1, len(ordenados) - 1)
    peso = posicao - abaixo
    return ordenados[abaixo] + (ordenados[acima] - ordenados[abaixo]) * peso


def faixa(precos: Sequence[Decimal]) -> tuple[Decimal, Decimal]:
    """Do 1º ao 3º quartil: a metade do meio dos preços.

    Os extremos ficam de fora de propósito. Uma peça de grife a R$ 1.200 no
    meio de camisetas a R$ 50 é o que esticaria uma faixa de mínimo a máximo
    até não dizer nada.
    """
    ordenados = sorted(precos)
    centavo = Decimal("0.01")
    return (
        _percentil(ordenados, Decimal("0.25")).quantize(centavo, ROUND_HALF_UP),
        _percentil(ordenados, Decimal("0.75")).quantize(centavo, ROUND_HALF_UP),
    )


def reais(valor: Decimal) -> str:
    """`R$ 1.234,50`."""
    inteiro, centavos = f"{valor:.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"


def justificativa(
    minimo: Decimal, maximo: Decimal, base: int, criterios: Sequence[str]
) -> str:
    """Texto curto que diz de onde a faixa veio, para o vendedor julgar."""
    parecidas = "Peças parecidas no catálogo"
    if criterios:
        parecidas += f" ({', '.join(criterios)})"
    if minimo == maximo:
        preco = f"por volta de {reais(minimo)}"
    else:
        preco = f"entre {reais(minimo)} e {reais(maximo)}"
    return f"{parecidas} costumam custar {preco}. Com base em {base} peças."


SEM_BASE = (
    "Ainda não há peças parecidas suficientes no catálogo para sugerir uma faixa. "
    "O preço fica a seu critério."
)
