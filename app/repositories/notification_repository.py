from datetime import datetime
from typing import TypedDict, cast

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.pagination import PageParams
from app.models.notification import FAVORITE_WHERE, Notification, NotificationType
from app.models.product import Product


class NotificationRow(TypedDict):
    id: int
    # O CHECK do banco só deixa gravar os tipos do Literal.
    type: NotificationType
    product_id: int
    product_name: str
    order_id: int | None
    created_at: datetime
    read_at: datetime | None


class NotificationRepository:
    """Persistência dos avisos in-app (back-end#261).

    Toda leitura e toda marcação recebem `user_id` e filtram por ele, como nos
    favoritos: aviso de outra pessoa não aparece nem é marcado. Nada aqui faz
    commit; quem cria o aviso grava no mesmo commit do evento.
    """

    def __init__(self, db: Session):
        self.db = db

    def add_sale(self, user_id: int, order_id: int, product_id: int) -> None:
        """Aviso da venda. Não precisa de proteção contra duplicar: só nasce na
        aprovação, e o pedido só sai de `em_analise` uma vez."""
        self.db.add(
            Notification(
                user_id=user_id,
                type="sale",
                product_id=product_id,
                order_id=order_id,
                created_at=utcnow_naive(),
            )
        )
        self.db.flush()

    def add_favorite(self, user_id: int, product_id: int, actor_id: int) -> None:
        """Aviso do favorito, uma vez por peça e por quem favoritou.

        `ON CONFLICT DO NOTHING` no índice único parcial: favoritar,
        desfavoritar e favoritar de novo não avisa outra vez, sem consulta
        prévia e sem corrida num duplo clique, como o próprio favorito. O
        `created_at` sai daqui, e não do `now()` do banco, pelo mesmo motivo do
        favorito: a ordem da lista não empata no mesmo segundo do SQLite.
        """
        insert = (
            pg_insert
            if self.db.get_bind().dialect.name == "postgresql"
            else sqlite_insert
        )
        self.db.execute(
            insert(Notification)
            .values(
                user_id=user_id,
                type="favorite",
                product_id=product_id,
                actor_id=actor_id,
                created_at=utcnow_naive(),
            )
            .on_conflict_do_nothing(
                index_elements=["product_id", "actor_id"],
                index_where=text(FAVORITE_WHERE),
            )
        )

    def list_for_user(
        self, user_id: int, params: PageParams
    ) -> tuple[list[NotificationRow], int]:
        """Avisos do usuário, mais recente primeiro, com o nome da peça."""
        do_usuario = Notification.user_id == user_id
        total = (
            self.db.scalar(select(func.count(Notification.id)).where(do_usuario)) or 0
        )
        rows = (
            self.db.execute(
                select(
                    Notification.id,
                    Notification.type,
                    Notification.product_id,
                    Product.name.label("product_name"),
                    Notification.order_id,
                    Notification.created_at,
                    Notification.read_at,
                )
                .join(Product, Product.id == Notification.product_id)
                .where(do_usuario)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .offset(params.offset)
                .limit(params.limit)
            )
            .mappings()
            .all()
        )
        return [cast(NotificationRow, dict(row)) for row in rows], total

    def count_unread(self, user_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id, Notification.read_at.is_(None)
                )
            )
            or 0
        )

    def exists_for_user(self, notification_id: int, user_id: int) -> bool:
        return (
            self.db.scalar(
                select(Notification.id).where(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                )
            )
            is not None
        )

    def mark_read(
        self, user_id: int, read_at: datetime, notification_id: int | None = None
    ) -> None:
        """Marca como lida uma, ou todas as do usuário sem `notification_id`.

        A que já estava lida mantém a data da primeira leitura.
        """
        stmt = update(Notification).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
        if notification_id is not None:
            stmt = stmt.where(Notification.id == notification_id)
        self.db.execute(stmt.values(read_at=read_at))

    def commit(self) -> None:
        self.db.commit()
