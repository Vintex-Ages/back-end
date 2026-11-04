from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.product_schema import FeedStoreResponse


class AddCartItemRequest(BaseModel):
    product_id: int = Field(gt=0)


class CartItemResponse(BaseModel):
    """Peça no carrinho. `available` é falso quando a peça deixou de estar à
    venda (ex.: vendida) depois de entrar no carrinho — ela continua listada,
    marcada, mas não entra no subtotal."""

    product_id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    available: bool

    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


class CartStoreInfo(FeedStoreResponse):
    """A loja no grupo do carrinho: a do feed, mais a chave Pix, a cidade e a
    logo (back-end#259). O checkout mostra para onde o dinheiro vai antes de a
    pessoa confirmar (RN-19). Não é o `FeedStoreResponse` direto porque o feed
    é público e não pode expor a chave Pix.

    `pix_key` e `city` são `None` quando a loja ainda não cadastrou."""

    pix_key: str | None
    city: str | None
    logo_url: str | None


class CartStoreResponse(BaseModel):
    """Um grupo do carrinho: as peças de uma loja e quanto pagar a ela.

    O carrinho nasce separado por loja porque o pagamento é Pix direto ao
    vendedor — cada grupo vira uma chave Pix e um valor exato no checkout.
    """

    store: CartStoreInfo
    items: list[CartItemResponse]
    subtotal: Decimal

    @field_serializer("subtotal")
    def serializar_subtotal(self, subtotal: Decimal) -> float:
        return float(subtotal)
