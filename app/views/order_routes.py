"""Pedidos do comprador (back-end#247).

Recurso do usuário logado — ADR 0001 §4, por isso `/users/me/orders`. Exige
login (RN-27), não exige ser vendedor.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.core.current_user import get_current_user_id
from app.database import get_db
from app.schemas.order_schema import OrderCreate, OrderResponse

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
