"""Números gerais da plataforma para a administradora (back-end#269).

Uma chamada traz tudo o que a tela abre: quantas lojas, usuários e peças
ativas, o volume vendido, a comissão acumulada e as vendas por loja. A tela não
calcula nada — os números chegam prontos daqui.

O caminho (`GET /api/admin/dashboard`) e os nomes dos campos são os do contrato
proposto pelo front (`front-end#431`). A back-end#269 fixou a origem de cada
número, não o formato da resposta; o front montou o service contra este
formato, e é aqui que ele fica fixado.

Valores em dinheiro saem como número, nunca string (#212).
"""

from decimal import Decimal

from pydantic import BaseModel, field_serializer


class StoreSalesEntry(BaseModel):
    """Uma loja e quanto ela vendeu em pedidos confirmados."""

    store_id: int
    store_name: str
    amount: Decimal

    @field_serializer("amount")
    def serializar_valor(self, valor: Decimal) -> float:
        return float(valor)


class AdminDashboardResponse(BaseModel):
    """O painel inteiro em uma resposta (RN-22 e RN-11).

    `sales_volume` é a soma do valor dos pedidos **confirmados** — o histórico
    de pagamento é a base (RN-22), não a peça. `commission_total` é a soma da
    comissão gravada em cada pedido: hoje 9% (RN-11), e o valor gravado é o que
    vale, para uma mudança de percentual não reescrever o passado.

    Sem venda nenhuma, os valores são zero e `sales_by_store` é vazio — a
    plataforma nova não é um erro.
    """

    stores_count: int
    users_count: int
    active_products_count: int
    sales_volume: Decimal
    commission_total: Decimal
    sales_by_store: list[StoreSalesEntry]

    @field_serializer("sales_volume", "commission_total")
    def serializar_valor(self, valor: Decimal) -> float:
        return float(valor)
