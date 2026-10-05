"""Carrinho do comprador (issue #147).

Recurso do usuário logado — ADR 0001 §4, por isso `/users/me/cart`. Exige
estar logado, não exige ser vendedor. `get_current_user_id` é o placeholder
de identidade da Sprint 2 (X-User-Id) até a #151 trocar por JWT de verdade.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.cart_controller import CartController
from app.core.current_user import get_current_user_id
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.cart_schema import AddCartItemRequest, CartStoreResponse

router = APIRouter(prefix="/users/me/cart", tags=["Cart"])


def get_controller(db: Session = Depends(get_db)) -> CartController:
    return CartController(db)


@router.get(
    "",
    response_model=Page[CartStoreResponse],
    summary="Carrinho agrupado por loja",
)
def get_cart(
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: CartController = Depends(get_controller),
) -> Page[CartStoreResponse]:
    return controller.get_cart(user_id, params)


@router.post(
    "/items",
    response_model=Page[CartStoreResponse],
    summary="Adiciona peça ao carrinho",
    responses={
        404: {"description": "PRODUCT_NOT_FOUND"},
        409: {"description": "PRODUCT_UNAVAILABLE"},
    },
)
def add_cart_item(
    data: AddCartItemRequest,
    user_id: int = Depends(get_current_user_id),
    controller: CartController = Depends(get_controller),
) -> Page[CartStoreResponse]:
    return controller.add_item(user_id, data.product_id)


@router.delete(
    "/items/{product_id}",
    response_model=Page[CartStoreResponse],
    summary="Remove peça do carrinho",
    responses={404: {"description": "CART_ITEM_NOT_FOUND"}},
)
def remove_cart_item(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: CartController = Depends(get_controller),
) -> Page[CartStoreResponse]:
    return controller.remove_item(user_id, product_id)
