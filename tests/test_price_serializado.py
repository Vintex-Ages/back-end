"""Como o `price` sai em JSON, rota por rota.

O `Decimal` do Pydantic serializa como **string** em JSON. Duas respostas
corrigem isso com `@field_serializer("price") -> float` e duas nao, entao o
mesmo campo chega como numero em algumas rotas e como string em outras.

Isso ja custou tempo duas vezes: o PR #127 anotou "price chega como string"
como se valesse para o feed (nao vale, o feed tem serializer), e o
`front-end#250` adicionou uma conversao no feed para um problema que nao
existe la. Nenhum teste dizia qual era qual -- este diz.

Nao muda comportamento. Fixa o que existe hoje para que mexer no serializer
quebre um teste em vez de quebrar o front em silencio. Uniformizar as quatro
(dando serializer as duas que nao tem) esta na `#212`, para depois da
apresentacao.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

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


@pytest.mark.parametrize(
    ("rotulo", "fabrica", "esperado"),
    [
        ("GET /api/products (feed, busca, sugestoes)", _feed, 99.9),
        ("GET /api/products/{id}", _detalhe, 149.9),
    ],
)
def test_price_sai_como_numero_onde_tem_field_serializer(
    rotulo: str, fabrica, esperado: float
) -> None:
    valor = _json(fabrica())["price"]

    assert isinstance(valor, float), f"{rotulo}: price veio {type(valor).__name__}"
    assert valor == esperado


@pytest.mark.parametrize(
    ("rotulo", "fabrica", "esperado"),
    [
        ("POST/PATCH/publish de rascunho", _rascunho, "10.50"),
        ("GET /api/stores/{id}/products", _peca_da_loja, "199.90"),
    ],
)
def test_price_sai_como_string_onde_nao_tem_field_serializer(
    rotulo: str, fabrica, esperado: str
) -> None:
    """Estas duas o front converte com `Number(...)`, e o tipo dele diz
    `number | string` por causa disto. Se ganharem serializer, o front segue
    funcionando -- mas o fixture dos testes dele fica desatualizado."""
    valor = _json(fabrica())["price"]

    assert isinstance(valor, str), f"{rotulo}: price veio {type(valor).__name__}"
    assert valor == esperado
