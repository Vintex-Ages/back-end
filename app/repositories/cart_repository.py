from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.models.cart import CartItem
from app.models.product import Product
from app.models.store import Store
from app.repositories.product_repository import ProductFeedRow, _feed_select


class CartRepository:
    """Persistência do carrinho (issue #147).

    Toda consulta recebe `user_id` e filtra por ele: não existe busca de item
    de carrinho sem dono, então ninguém enxerga o carrinho de outra pessoa.
    A loja de cada item vem de `Product.store_id` por join.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_item(self, user_id: int, product_id: int) -> CartItem | None:
        return self.db.scalar(
            select(CartItem).where(
                CartItem.user_id == user_id, CartItem.product_id == product_id
            )
        )

    def add_item(self, user_id: int, product_id: int) -> CartItem:
        item = CartItem(user_id=user_id, product_id=product_id)
        self.db.add(item)
        self.db.flush()
        return item

    def remove_item(self, item: CartItem) -> None:
        self.db.delete(item)
        self.db.flush()

    def count_stores(self, user_id: int) -> int:
        """Quantas lojas diferentes têm peça no carrinho — é o `total` da
        paginação, que pagina lojas e não itens."""
        stmt = (
            select(func.count(func.distinct(Product.store_id)))
            .select_from(CartItem)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.user_id == user_id)
        )
        return self.db.scalar(stmt) or 0

    def list_store_ids(self, user_id: int, params: PageParams) -> list[int]:
        """Lojas da página pedida, em ordem de nome. Paginar por loja garante
        que uma loja nunca fica partida entre duas páginas."""
        stmt = (
            select(Store.id)
            .join(Product, Product.store_id == Store.id)
            .join(CartItem, CartItem.product_id == Product.id)
            .where(CartItem.user_id == user_id)
            .group_by(Store.id, Store.name)
            .order_by(Store.name.asc(), Store.id.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_items_for_stores(
        self, user_id: int, store_ids: list[int]
    ) -> list[ProductFeedRow]:
        """Peças do carrinho dessas lojas, numa consulta só (nunca uma por
        loja). Reusa a base de listagem de peça do `ProductRepository`."""
        if not store_ids:
            return []
        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            .join(CartItem, CartItem.product_id == Product.id)
            .where(CartItem.user_id == user_id, Store.id.in_(store_ids))
            .order_by(CartItem.created_at.asc(), CartItem.id.asc())
        )
        rows = self.db.execute(stmt).mappings().all()
        return [cast(ProductFeedRow, dict(row)) for row in rows]
