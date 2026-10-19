"""Schemas do pedido (back-end#247).

Os valores em dinheiro saem como número no JSON. `Decimal` do Pydantic
serializa como string sem `@field_serializer`, e isso já custou dois PRs ao
projeto (#212).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, field_serializer, field_validator


class DeliveryAddress(BaseModel):
    """Endereço de entrega, copiado para o pedido na compra.

    Mesmos nomes e limites do `StoreAddressCreate` e das colunas `delivery_*`
    de `orders`: `zip_code` e `neighborhood`, e não `cep`/`district`. É um
    schema próprio, e não o da loja, porque o endereço é do comprador.
    """

    zip_code: str = Field(min_length=1, max_length=10)
    street: str = Field(min_length=1, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    complement: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)


class OrderCreate(BaseModel):
    product_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1)
    delivery_address: DeliveryAddress

    @field_validator("product_ids")
    @classmethod
    def sem_repeticao(cls, product_ids: list[int]) -> list[int]:
        # Peça é única (RN-46): a mesma peça duas vezes é erro de quem chama.
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("A mesma peça não pode aparecer duas vezes.")
        return product_ids


class OrderStoreResponse(BaseModel):
    """A loja e a chave Pix para onde o comprador paga (RN-19 e RN-20)."""

    id: int
    name: str
    pix_key: str


class OrderItemResponse(BaseModel):
    product_id: int
    name: str
    price: Decimal
    cover_image_url: str | None

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


class OrderHistoryResponse(BaseModel):
    status: str
    at: datetime


class OrderResponse(BaseModel):
    id: int
    store: OrderStoreResponse
    items: list[OrderItemResponse]
    product_amount: Decimal
    platform_fee: Decimal
    total_amount: Decimal
    status: str
    history: list[OrderHistoryResponse]
    delivery_address: DeliveryAddress
    # Sempre `null` na criação: o comprovante é anexado depois (back-end#249).
    payment: None = None
    expires_at: datetime
    created_at: datetime

    @field_serializer("product_amount", "platform_fee", "total_amount")
    def serializar_valor(self, valor: Decimal) -> float:
        return float(valor)
