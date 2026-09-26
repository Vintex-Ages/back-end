from collections.abc import Sequence
from decimal import Decimal
from typing import TypedDict, cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store


class ProductFeedRow(TypedDict):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    store_id: int
    store_name: str


def _feed_select() -> Select[tuple[object, ...]]:
    """Base comum a qualquer listagem de peça (feed, busca) — o resultado
    sempre bate com `ProductFeedRow`, incluindo a subquery da capa. Quem
    chama ainda adiciona `join`/`where`/`order_by` próprios."""
    cover_image_url = (
        select(ProductImage.image_url)
        .where(ProductImage.product_id == Product.id)
        .order_by(ProductImage.position.asc(), ProductImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    return select(
        Product.id,
        Product.name,
        Product.price,
        cover_image_url.label("cover_image_url"),
        Product.status,
        Store.id.label("store_id"),
        Store.name.label("store_name"),
    )


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_seller(self, product_id: int, user_id: int) -> Product | None:
        """Peça filtrada pelo dono (join `Store` → `Seller`).

        Não existe `get_by_id` sem dono: quem chama sempre sabe quem está
        pedindo (`get_current_user_id`), e um `Product` de outro vendedor
        deve responder igual a "não existe" (`PRODUCT_NOT_FOUND`), nunca
        vazar que a peça existe mas não é dele.
        """
        return self.db.scalar(
            select(Product)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Product.id == product_id, Seller.user_id == user_id)
        )

    def get_active_feed(self, params: PageParams) -> tuple[list[ProductFeedRow], int]:
        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            .where(Product.status == "ativo")
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(ProductFeedRow, dict(row)) for row in rows], total

    def find_similar(
        self, query_embedding: Sequence[float], limit: int = 5
    ) -> list[ProductFeedRow]:
        """Peças ativas mais próximas do vetor da pergunta (BE-US027-3, back-end#149).

        Só peças com embedding entram na ordenação — sem isso, `ORDER BY
        cosine_distance(NULL, ...)` derruba peças sem posição pro fim de
        forma indefinida em vez de excluí-las. Nunca inventa peça: só o que
        já existe no catálogo real pode aparecer aqui.
        """
        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            .where(Product.status == "ativo", Product.embedding.is_not(None))
            .order_by(Product.embedding.cosine_distance(list(query_embedding)))
            .limit(limit)
        )
        rows = self.db.execute(stmt).mappings().all()
        return [cast(ProductFeedRow, dict(row)) for row in rows]
