from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.errors import ErrorCode, NotFound
from app.core.pagination import PageParams
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification_schema import NotificationPage, NotificationResponse


class NotificationController:
    """Avisos in-app do usuário logado (back-end#261, RN-84 e RN-85).

    Aqui só se lê e se marca como lido. Os avisos nascem nos próprios eventos:
    a venda em `PaymentReviewController.approve` e o favorito em
    `FavoriteController.add_favorite`, no mesmo commit de cada um.
    """

    def __init__(self, db: Session):
        self.notifications = NotificationRepository(db)

    def list_mine(self, user_id: int, params: PageParams) -> NotificationPage:
        rows, total = self.notifications.list_for_user(user_id, params)
        return NotificationPage(
            items=[
                NotificationResponse(
                    id=row["id"],
                    type=row["type"],
                    product_id=row["product_id"],
                    product_name=row["product_name"],
                    order_id=row["order_id"],
                    created_at=row["created_at"],
                    is_read=row["read_at"] is not None,
                )
                for row in rows
            ],
            page=params.page,
            page_size=params.page_size,
            total=total,
            unread_count=self.notifications.count_unread(user_id),
        )

    def mark_read(self, user_id: int, notification_id: int) -> None:
        """Marcar de novo a que já está lida responde igual. Aviso de outra
        pessoa responde 404, igual a inexistente: um 403 confirmaria o id."""
        if not self.notifications.exists_for_user(notification_id, user_id):
            raise NotFound(
                "Notificação não encontrada.", code=ErrorCode.NOTIFICATION_NOT_FOUND
            )
        self.notifications.mark_read(user_id, utcnow_naive(), notification_id)
        self.notifications.commit()

    def mark_all_read(self, user_id: int) -> None:
        self.notifications.mark_read(user_id, utcnow_naive())
        self.notifications.commit()
