"""Schemas dos avisos in-app (back-end#261).

O formato segue o modelo do front (`front-end/src/types/notification.ts`):
`type`, a peça, a data e se já foi lida. Quem favoritou não sai: o anunciante
sabe que alguém favoritou, não quem.
"""

from datetime import datetime

from pydantic import BaseModel

from app.core.pagination import Page
from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: int
    type: NotificationType
    product_id: int
    product_name: str
    # Só na venda: o pedido aprovado.
    order_id: int | None
    created_at: datetime
    is_read: bool


class NotificationPage(Page[NotificationResponse]):
    """A página e a contagem de não lidas de todas as páginas, para o badge
    não depender de qual página a tela abriu."""

    unread_count: int
