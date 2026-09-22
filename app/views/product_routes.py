from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_management_schema import (
    ProductManagementPage,
    ProductManagementResponse,
    ProductUpdate,
)
from app.schemas.product_schema import FeedResponse, ProductDetailResponse

router = APIRouter(prefix="/products", tags=["Products"])
seller_router = APIRouter(prefix="/seller/products", tags=["Seller products"])


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


def list_seller_products(
    status: Literal["ativo", "vendido", "despublicado"] | None = Query(None),
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementPage:
    return controller.list_for_seller(user_id, params, status)


router.add_api_route(
    "/mine",
    list_seller_products,
    methods=["GET"],
    response_model=ProductManagementPage,
)
router.add_api_route(
    "/seller",
    list_seller_products,
    methods=["GET"],
    response_model=ProductManagementPage,
)
seller_router.add_api_route(
    "",
    list_seller_products,
    methods=["GET"],
    response_model=ProductManagementPage,
)


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


@router.api_route(
    "/{product_id}",
    methods=["PATCH", "PUT"],
    response_model=ProductManagementResponse,
)
def update_product(
    product_id: int,
    data: ProductUpdate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.update(product_id, user_id, data)
    )


@router.post("/{product_id}/unpublish", response_model=ProductManagementResponse)
def unpublish_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.set_status(product_id, user_id, "despublicado")
    )


@router.post("/{product_id}/publish", response_model=ProductManagementResponse)
def publish_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementResponse:
    return ProductManagementResponse.model_validate(
        controller.set_status(product_id, user_id, "ativo")
    )
