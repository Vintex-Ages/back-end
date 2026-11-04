from collections.abc import Collection
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.pagination import PageParams
from app.models.favorite import Favorite
from app.models.product import Product
from app.models.store import Store
from app.repositories.product_repository import ProductFeedRow, _feed_select


class FavoriteRepository:
    """Persistência dos favoritos (back-end#252).

    Toda consulta recebe `user_id` e filtra por ele, como no carrinho: ninguém
    enxerga nem mexe nos favoritos de outra pessoa. Nada aqui faz commit.
    """

    def __init__(self, db: Session):
        self.db = db

    def add(self, user_id: int, product_id: int) -> None:
        """`INSERT ... ON CONFLICT DO NOTHING` na chave composta: favoritar o
        que já está favoritado não faz nada, sem consulta prévia e sem corrida
        num duplo clique. O `created_at` sai daqui, e não do `now()` do banco,
        para a ordem da lista não empatar no mesmo segundo do SQLite."""
        insert = (
            pg_insert
            if self.db.get_bind().dialect.name == "postgresql"
            else sqlite_insert
        )
        self.db.execute(
            insert(Favorite)
            .values(user_id=user_id, product_id=product_id, created_at=utcnow_naive())
            .on_conflict_do_nothing(index_elements=["user_id", "product_id"])
        )

    def remove(self, user_id: int, product_id: int) -> None:
        """Apagar o que não existe não é erro: o `DELETE` só não acha linha."""
        self.db.execute(
            delete(Favorite).where(
                Favorite.user_id == user_id, Favorite.product_id == product_id
            )
        )

    def list_for_user(
        self, user_id: int, statuses: Collection[str], params: PageParams
    ) -> tuple[list[ProductFeedRow], int]:
        """Peças favoritadas nestas situações, mais recente primeiro, no
        formato da listagem de peça (`_feed_select`, a mesma base do feed)."""
        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user_id, Product.status.in_(statuses))
            .order_by(Favorite.created_at.desc(), Favorite.product_id.desc())
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(ProductFeedRow, dict(row)) for row in rows], total
