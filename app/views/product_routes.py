from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.errors import ValidationError
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_schema import (
    FeedResponse,
    ProductAIStatusResponse,
    ProductFilters,
)

router = APIRouter(prefix="/products", tags=["Products"])

# Recurso do usuário logado (dono da peça) — ADR 0001 §4. A análise de IA de
# uma peça (inclusive sugestões ainda em rascunho) não é dado público; fica
# fora do router acima, que é só para o feed. `get_current_user_id` é o
# placeholder de identidade da Sprint 2 (X-User-Id) até a #151 trocar por JWT
# de verdade — o controller já filtra a peça pelo dono.
me_router = APIRouter(prefix="/users/me/products", tags=["Products"])


def get_controller(db: Session = Depends(get_db)) -> ProductController:
    return ProductController(db)


def product_filters(
    category: str | None = Query(None),
    price_min: Decimal | None = Query(None),
    price_max: Decimal | None = Query(None),
    size: str | None = Query(None),
    brand: str | None = Query(None),
    condition: str | None = Query(None),
    color: str | None = Query(None),
) -> ProductFilters:
    try:
        return ProductFilters(
            category=category,
            price_min=price_min,
            price_max=price_max,
            size=size,
            brand=brand,
            condition=condition,
            color=color,
        )
    except PydanticValidationError as exc:
        fields = {
            ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
            for error in exc.errors()
        }
        raise ValidationError("Dados inválidos na requisição.", fields=fields) from exc


@router.get("", response_model=FeedResponse)
def list_products(
    params: PageParams = Depends(page_params),
    filters: ProductFilters = Depends(product_filters),
    sort: Literal["recent"] = Query(
        "recent", description="Ordenação do feed; atualmente apenas recentes."
    ),
    controller: ProductController = Depends(get_controller),
) -> FeedResponse:
    return controller.get_feed(params, filters)


@me_router.get("/{product_id}/ai-status", response_model=ProductAIStatusResponse)
def get_product_ai_status(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductAIStatusResponse:
    return controller.get_ai_status(product_id, user_id)
