"""Comissão da Vintex — 9%, num lugar só.

A taxa é a dor central da stakeholder: ela vende no Enjoei e fica com 60% do
que vende. Os 9% são a metade da taxa de lá, e aparecem em três lugares do
produto (resumo financeiro do vendedor, valor líquido no formulário da peça,
carrinho). O front já centralizou do lado dele em `utils/commission`; este é o
equivalente no back, para que mudar a taxa seja mudar uma linha.

Arredonda para centavo em `ROUND_HALF_UP`, e o líquido sai por subtração — não
por um segundo arredondamento — para que `comissão + líquido == bruto` sempre.
"""

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")
COMISSAO_VINTEX = Decimal("0.09")


def dividir(bruto: Decimal) -> tuple[Decimal, Decimal]:
    """Devolve `(comissão, líquido)` a partir do bruto."""
    comissao = (bruto * COMISSAO_VINTEX).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return comissao, bruto - comissao
