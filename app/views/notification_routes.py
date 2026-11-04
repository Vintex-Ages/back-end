"""Avisos in-app do usuário logado (back-end#261).

Recurso do usuário logado, ADR 0001 §4, por isso `/users/me/notifications`.
Exige estar logado (RN-27). Marcar como lida não tem corpo nos dois sentidos e
é idempotente: marcar de novo responde igual.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.notification_controller import NotificationController
from app.core.current_user import get_current_user_id
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.notification_schema import NotificationPage

router = APIRouter(prefix="/users/me/notifications", tags=["Notifications"])


def get_controller(db: Session = Depends(get_db)) -> NotificationController:
    return NotificationController(db)


@router.get(
    "",
    response_model=NotificationPage,
    summary="Avisos do usuário, mais recente primeiro, com a contagem de não lidos",
)
def list_notifications(
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: NotificationController = Depends(get_controller),
) -> NotificationPage:
    return controller.list_mine(user_id, params)


@router.post(
    "/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marca todos os avisos como lidos",
)
def mark_all_read(
    user_id: int = Depends(get_current_user_id),
    controller: NotificationController = Depends(get_controller),
) -> None:
    controller.mark_all_read(user_id)


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marca o aviso como lido",
    responses={404: {"description": "NOTIFICATION_NOT_FOUND"}},
)
def mark_read(
    notification_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: NotificationController = Depends(get_controller),
) -> None:
    controller.mark_read(user_id, notification_id)
