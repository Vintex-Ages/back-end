"""Rotas da administradora (back-end#61).

A guarda fica no router, e não em cada rota: toda rota que entrar aqui (a fila
de comprovantes da #250, aprovar e rejeitar da #251) nasce exigindo o papel.
Esquecer o `Depends` numa rota nova não abre a rota (RN-32).
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.payment_review_controller import PaymentReviewController
from app.core.security import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin_payment_schema import PaymentReviewResponse, RejectRequest

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def get_review_controller(db: Session = Depends(get_db)) -> PaymentReviewController:
    return PaymentReviewController(db)


_ERROS_DA_VALIDACAO: dict[int | str, dict[str, Any]] = {
    403: {"description": "ADMIN_REQUIRED"},
    404: {"description": "ORDER_NOT_FOUND"},
    409: {"description": "ORDER_NOT_IN_REVIEW: o pedido não está em análise"},
}


@router.post(
    "/payments/{order_id}/approve",
    response_model=PaymentReviewResponse,
    # Sem `rejection_reason: null` na resposta do approve: o contrato não traz
    # a chave.
    response_model_exclude_none=True,
    summary="Aprova o comprovante e confirma o pedido",
    responses=_ERROS_DA_VALIDACAO,
)
def approve_payment(
    order_id: int,
    admin: User = Depends(require_admin),
    controller: PaymentReviewController = Depends(get_review_controller),
) -> PaymentReviewResponse:
    return controller.approve(order_id, admin)


@router.post(
    "/payments/{order_id}/reject",
    response_model=PaymentReviewResponse,
    summary="Rejeita o comprovante com motivo e devolve o pedido ao comprador",
    responses={**_ERROS_DA_VALIDACAO, 422: {"description": "motivo vazio"}},
)
def reject_payment(
    order_id: int,
    data: RejectRequest,
    admin: User = Depends(require_admin),
    controller: PaymentReviewController = Depends(get_review_controller),
) -> PaymentReviewResponse:
    return controller.reject(order_id, admin, data.reason)
