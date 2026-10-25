"""Rotas da administradora (back-end#61).

A guarda fica no router, e não em cada rota: toda rota que entrar aqui (a fila
de comprovantes da #250, aprovar e rejeitar da #251, o arquivo do comprovante
da #244) nasce exigindo o papel.
Esquecer o `Depends` numa rota nova não abre a rota (RN-32).
"""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.controllers.payment_review_controller import PaymentReviewController
from app.core.security import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin_payment_schema import PaymentReviewResponse, RejectRequest
from app.services.media_storage import MediaStorage
from app.views.media_routes import get_media_storage

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


@router.get(
    "/payments/{order_id}/receipt",
    summary="O arquivo do comprovante vigente, com o tipo original",
    response_class=Response,
    responses={
        200: {
            "content": {"image/*": {}, "application/pdf": {}},
            "description": "O arquivo, não JSON",
        },
        403: {"description": "ADMIN_REQUIRED: inclusive o comprador dono do pedido"},
        404: {"description": "ORDER_NOT_FOUND · RECEIPT_NOT_FOUND"},
    },
)
def get_payment_receipt(
    order_id: int,
    controller: PaymentReviewController = Depends(get_review_controller),
    storage: MediaStorage = Depends(get_media_storage),
) -> Response:
    conteudo, content_type = controller.read_receipt(order_id, storage)
    return Response(
        content=conteudo,
        media_type=content_type,
        headers={
            # Dado bancário: nada de cache compartilhado nem em disco.
            "Cache-Control": "private, no-store",
            # O tipo é o que o comprador declarou no envio; sem `nosniff` o
            # navegador pode renderizar como HTML um arquivo mandado como
            # imagem, servido da nossa origem (o mesmo motivo da rota pública).
            "X-Content-Type-Options": "nosniff",
        },
    )


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
