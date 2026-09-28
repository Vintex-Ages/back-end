from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.errors import ValidationError
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_management_schema import (
    ProductManagementPage,
    ProductManagementResponse,
    ProductUpdate,
)
from app.schemas.product_schema import (
    FeedResponse,
    ProductAIStatusResponse,
    ProductDetailResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFilters,
)

router = APIRouter(prefix="/products", tags=["Products"])

# Recurso do usuário logado (ADR 0001 §4): peças do próprio vendedor.
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
    q: str | None = Query(
        None, max_length=200, description="Termo de busca; ignora acento e caixa."
    ),
    filters: ProductFilters = Depends(product_filters),
    sort: Literal["recent"] = Query(
        "recent", description="Ordenação do feed; atualmente apenas recentes."
    ),
    controller: ProductController = Depends(get_controller),
) -> FeedResponse:
    return controller.get_feed(params, filters, q=q)


@me_router.get("", response_model=ProductManagementPage)
def list_seller_products(
    status: Literal["ativo", "vendido", "despublicado"] | None = Query(None),
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementPage:
    return controller.list_for_seller(user_id, params, status)


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Detalhe da peça",
    responses={404: {"description": "PRODUCT_NOT_FOUND"}},
)
def get_product_detail(
    product_id: int,
    controller: ProductController = Depends(get_controller),
) -> ProductDetailResponse:
    return controller.get_detail(product_id)


@me_router.patch("/{product_id}", response_model=ProductManagementResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.update(product_id, user_id, data)
    )


@me_router.post("/{product_id}/unpublish", response_model=ProductManagementResponse)
def unpublish_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.set_status(product_id, user_id, "despublicado")
    )


# Rota distinta de `POST /users/me/products/{id}/publish` (#159): aquela
# publica um rascunho pela primeira vez (exige foto); esta só reativa uma peça
# despublicada — o controller recusa rascunho aqui.
@me_router.post("/{product_id}/republish", response_model=ProductManagementResponse)
def republish_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.set_status(product_id, user_id, "ativo")
    )


@router.patch("/{product_id}", response_model=ProductDraftResponse)
def update_draft(
    product_id: int,
    data: ProductDraftUpdate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.update_draft(user_id, product_id, data)


@me_router.post(
    "", response_model=ProductDraftResponse, status_code=status.HTTP_201_CREATED
)
def create_draft(
    data: ProductDraftCreate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.create_draft(user_id, data)


@me_router.post("/{product_id}/publish", response_model=ProductDraftResponse)
def publish_draft(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.publish(user_id, product_id)


@me_router.get("/{product_id}/ai-status", response_model=ProductAIStatusResponse)
def get_product_ai_status(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductAIStatusResponse:
    return controller.get_ai_status(product_id, user_id)
