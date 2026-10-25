"""Pedidos do comprador (back-end#247 e back-end#248).

Recurso do usuário logado — ADR 0001 §4, por isso `/users/me/orders`. Exige
login (RN-27), não exige ser vendedor.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.core.current_user import get_current_user_id
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.order_schema import OrderCreate, OrderListItemResponse, OrderResponse

router = APIRouter(prefix="/users/me/orders", tags=["Orders"])


def get_controller(db: Session = Depends(get_db)) -> OrderController:
    return OrderController(db)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria o pedido e reserva as peças",
    responses={
        409: {"description": "MIXED_STORES · PIECE_UNAVAILABLE · STORE_WITHOUT_PIX"},
    },
)
def create_order(
    data: OrderCreate,
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> OrderResponse:
    return controller.create(user_id, data)


@router.get(
    "",
    response_model=Page[OrderListItemResponse],
    summary="Lista os pedidos de quem está logado, mais recente primeiro",
)
def list_my_orders(
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> Page[OrderListItemResponse]:
    return controller.list_mine(user_id, params)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Detalhe do pedido, com a chave Pix e a linha do tempo",
    responses={404: {"description": "ORDER_NOT_FOUND: inexistente ou de outra pessoa"}},
)
def get_my_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> OrderResponse:
    return controller.get_mine(user_id, order_id)
