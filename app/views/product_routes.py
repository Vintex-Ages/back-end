from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_schema import (
    FeedResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
)

router = APIRouter(prefix="/products", tags=["Products"])

# Recurso do usuário logado (ADR 0001 §4). Só create/publish moraram aqui;
# o PATCH de edição continua em /products/{id} até a #157 entrar — ela leva
# esse PATCH pra cá cobrindo rascunho e publicada com um if no status.
me_router = APIRouter(prefix="/users/me/products", tags=["Products"])


def get_controller(db: Session = Depends(get_db)) -> ProductController:
    return ProductController(db)


@router.get("", response_model=FeedResponse)
def list_products(
    params: PageParams = Depends(page_params),
    sort: Literal["recent"] = Query(
        "recent", description="Ordenação do feed; atualmente apenas recentes."
    ),
    controller: ProductController = Depends(get_controller),
) -> FeedResponse:
    return controller.get_feed(params)


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
