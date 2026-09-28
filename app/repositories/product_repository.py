from collections.abc import Sequence
from decimal import Decimal
from typing import TypedDict, cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.pagination import Page, PageParams, paginate
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.schemas.product_management_schema import ProductManagementResponse
from app.schemas.product_schema import ProductFilters

# Mesma expressao do indice ix_products_search_trgm (migration 0f9a7f647244).
# Se mudar aqui sem mudar la, o Postgres para de usar o indice e a busca vira
# varredura da tabela inteira.
TEXTO_BUSCAVEL = func.immutable_unaccent(
    func.lower(
        func.coalesce(Product.name, "")
        + " "
        + func.coalesce(Product.description, "")
        + " "
        + func.coalesce(Product.brand, "")
        + " "
        + func.coalesce(Product.category, "")
    )
)


class ProductFeedRow(TypedDict):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    store_id: int
    store_name: str
    store_verified: bool


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
    # Selo "Confiável" (#143): subquery pelo `Store` que o chamador já juntou,
    # para ninguém precisar lembrar de um join extra com `Seller`.
    store_verified = (
        select(Seller.verified).where(Seller.id == Store.seller_id).scalar_subquery()
    )
    return select(
        Product.id,
        Product.name,
        Product.price,
        cover_image_url.label("cover_image_url"),
        Product.status,
        Store.id.label("store_id"),
        Store.name.label("store_name"),
        store_verified.label("store_verified"),
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

    def get_active_feed(
        self, params: PageParams, filters: ProductFilters, q: str | None = None
    ) -> tuple[list[ProductFeedRow], int]:
        conditions = [Product.status == "ativo"]
        filter_columns = {
            "category": Product.category,
            "size": Product.size,
            "brand": Product.brand,
            "condition": Product.condition,
            "color": Product.color,
        }
        for field_name, column in filter_columns.items():
            value = getattr(filters, field_name)
            if value is not None:
                normalized_column = func.lower(column)
                normalized_value = func.lower(value)
                if self.db.get_bind().dialect.name == "postgresql":
                    normalized_column = func.immutable_unaccent(normalized_column)
                    normalized_value = func.immutable_unaccent(normalized_value)
                conditions.append(normalized_column == normalized_value)
        if filters.price_min is not None:
            conditions.append(Product.price >= filters.price_min)
        if filters.price_max is not None:
            conditions.append(Product.price <= filters.price_max)

        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            .where(*conditions)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        if q:
            stmt = stmt.where(
                TEXTO_BUSCAVEL.contains(func.immutable_unaccent(func.lower(q)))
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(ProductFeedRow, dict(row)) for row in rows], total

    def list_for_seller(
        self, user_id: int, params: PageParams, status: str | None = None
    ) -> Page[object]:
        stmt = (
            select(Product)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        if status is not None:
            stmt = stmt.where(Product.status == status)
        return paginate(
            self.db,
            stmt,
            params,
            item_schema=ProductManagementResponse,
        )

    def get_store_for_user(self, user_id: int) -> Store | None:
        """Loja de quem está criando/editando — um vendedor, uma loja."""
        stmt = (
            select(Store)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id)
        )
        return self.db.scalars(stmt).first()

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

    def get_detail_by_id(self, product_id: int) -> Product | None:
        stmt = (
            select(Product)
            .options(
                joinedload(Product.store).joinedload(Store.address),
                joinedload(Product.store).joinedload(Store.seller),
                selectinload(Product.images),
            )
            .where(Product.id == product_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def save(self, product: Product) -> Product:
        self.db.flush()
        return product

    def get_by_id(self, product_id: int) -> Product | None:
        """Como `get_detail_by_id`, mas com `ai_corrections` — usado pelo
        fluxo de rascunho (`_get_owned_draft`), que devolve o histórico de
        correções da IA junto com a peça."""
        stmt = (
            select(Product)
            .options(
                joinedload(Product.store).joinedload(Store.address),
                joinedload(Product.store).joinedload(Store.seller),
                selectinload(Product.images),
                selectinload(Product.ai_corrections),
            )
            .where(Product.id == product_id)
        )
        return self.db.scalars(stmt).one_or_none()

    def create(self, product: Product) -> Product:
        self.db.add(product)
        self.db.flush()
        return product

    def commit(self) -> None:
        self.db.commit()
