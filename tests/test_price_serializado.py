"""`price` sai como numero em JSON em toda resposta que o tem.

O `Decimal` do Pydantic serializa como **string** se ninguem interferir, e por
um tempo duas respostas tinham `@field_serializer("price") -> float` e tres nao.
A mesma peca chegava ao front como numero pelo feed e como string pela lista do
vendedor, pela loja e pelo rascunho.

Isso custou tempo duas vezes: o PR #127 anotou "price chega como string" como se
valesse para o feed (nao vale, o feed sempre teve serializer) e o
`front-end#250` adicionou uma conversao no feed para um problema que nao existia
la. A `#212` uniformizou; este teste e o que impede a divergencia de voltar.

Quem adicionar um schema com `price` adiciona uma linha na lista abaixo. Sem
serializer, o teste falha -- que e o ponto.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.cart_schema import CartItemResponse
from app.schemas.product_management_schema import ProductManagementResponse
from app.schemas.product_schema import (
    FeedStoreResponse,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductDraftResponse,
    ProductFeedItemResponse,
    ProductStoreResponse,
)
from app.schemas.store_schema import StoreProductItemResponse

AGORA = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)


def _json(modelo: object) -> dict:
    return json.loads(modelo.model_dump_json())  # type: ignore[attr-defined]


def _feed() -> ProductFeedItemResponse:
    return ProductFeedItemResponse(
        id=41,
        name="Jaqueta",
        price=Decimal("99.90"),
        cover_image_url=None,
        store=FeedStoreResponse(id=7, name="Aurora", verified=False),
        status="ativo",
    )


def _detalhe() -> ProductDetailResponse:
    return ProductDetailResponse(
        id=41,
        name="Jaqueta",
        description="d",
        category="Roupas",
        style="Vintage",
        brand="b",
        color="Preto",
        size="M",
        condition="Usado",
        price=Decimal("149.90"),
        status="ativo",
        city="Porto Alegre",
        state="RS",
        media=[],
        store=ProductDetailStoreResponse(
            id=7, name="Aurora", logo_url=None, verified=False
        ),
    )


def _rascunho() -> ProductDraftResponse:
    return ProductDraftResponse(
        id=41,
        name="Jaqueta",
        description=None,
        category=None,
        style=None,
        brand=None,
        color=None,
        size=None,
        condition=None,
        price=Decimal("10.50"),
        quantity=1,
        status="rascunho",
        store=ProductStoreResponse(id=7, name="Aurora", city="Porto Alegre"),
        images=[],
        ai_corrections=[],
    )


def _peca_da_loja() -> StoreProductItemResponse:
    return StoreProductItemResponse(
        id=41,
        name="Jaqueta",
        price=Decimal("199.90"),
        cover_image_url=None,
        status="ativo",
    )


def _peca_do_vendedor() -> ProductManagementResponse:
    return ProductManagementResponse(
        id=41,
        name="Jaqueta",
        description=None,
        category=None,
        style=None,
        brand=None,
        color=None,
        size=None,
        condition=None,
        price=Decimal("348.59"),
        quantity=1,
        status="despublicado",
    )


def _item_do_carrinho() -> CartItemResponse:
    return CartItemResponse(
        product_id=41,
        name="Jaqueta",
        price=Decimal("374.79"),
        cover_image_url=None,
        status="ativo",
        available=True,
    )


@pytest.mark.parametrize(
    ("rotulo", "fabrica", "esperado"),
    [
        ("GET /api/products (feed, busca, sugestoes)", _feed, 99.9),
        ("GET /api/products/{id}", _detalhe, 149.9),
        ("POST/PATCH/publish/unpublish de peca", _rascunho, 10.5),
        ("GET /api/stores/{id}/products", _peca_da_loja, 199.9),
        ("GET /api/users/me/products", _peca_do_vendedor, 348.59),
        ("GET /api/users/me/cart", _item_do_carrinho, 374.79),
    ],
)
def test_price_sai_como_numero_em_toda_resposta(
    rotulo: str, fabrica, esperado: float
) -> None:
    valor = _json(fabrica())["price"]

    assert isinstance(valor, float), f"{rotulo}: price veio {type(valor).__name__}"
    assert valor == esperado
