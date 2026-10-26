"""Consultas da loja: as publicas (back-end#142) e as do proprio vendedor
(back-end#141). Um vendedor tem uma loja (decisao de modelagem 1:1)."""

from typing import TypedDict, cast

from sqlalchemy import ColumnElement, ScalarSelect, case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.pagination import PageParams
from app.models.address import Address
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store


class StoreMetricsRow(TypedDict):
    active_count: int
    products_sold: int


class StoreListRow(TypedDict):
    id: int
    name: str
    description: str | None
    logo_url: str | None
    verified: bool
    city: str | None
    state: str | None
    active_count: int


def _active_count() -> ScalarSelect[int]:
    """Peças `ativo` da loja da consulta externa (back-end#256). Correlacionada
    com o `Store`, então vem na mesma consulta da listagem."""
    return (
        select(func.count(Product.id))
        .where(Product.store_id == Store.id, Product.status == "ativo")
        .correlate(Store)
        .scalar_subquery()
    )


class StoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, store_id: int) -> Store | None:
        """Loja pública — já traz `seller` (pro selo) e `address` numa consulta só."""
        return self.db.scalar(
            select(Store)
            .options(joinedload(Store.seller), joinedload(Store.address))
            .where(Store.id == store_id)
        )

    def get_metrics(self, store_id: int) -> StoreMetricsRow:
        """Peças ativas e vendidas, numa consulta agregada só.

        A contagem de ativas era de tudo que não fosse rascunho, incluindo
        vendida e despublicada, e o front a mostra como "peças ativas": loja
        que vendeu metade do estoque anunciava o dobro do que tinha
        (back-end#256). Agora é só `ativo`, como o `active_count` da listagem.
        """
        row = self.db.execute(
            select(
                func.coalesce(
                    func.sum(case((Product.status == "ativo", 1), else_=0)), 0
                ).label("active_count"),
                func.coalesce(
                    func.sum(case((Product.status == "vendido", 1), else_=0)), 0
                ).label("products_sold"),
            ).where(Product.store_id == store_id)
        ).one()
        return StoreMetricsRow(
            active_count=int(row.active_count),
            products_sold=int(row.products_sold),
        )

    def list_stores(
        self, q: str | None, params: PageParams
    ) -> tuple[list[StoreListRow], int]:
        """Brechós em ordem de nome, com a busca por parte do nome (back-end#256).

        Só o nome: cidade fica de fora, declarado na issue. Sem diferenciar
        maiúscula, e no Postgres também sem acento. `outerjoin` no endereço:
        loja sem endereço continua na lista, com `city`/`state` nulos.
        """
        stmt = (
            select(
                Store.id,
                Store.name,
                Store.description,
                Store.logo_url,
                Seller.verified,
                Address.city,
                Address.state,
                _active_count().label("active_count"),
            )
            .join(Seller, Seller.id == Store.seller_id)
            .outerjoin(Address, Address.id == Store.address_id)
            .order_by(Store.name.asc(), Store.id.asc())
        )
        if q:
            stmt = stmt.where(
                self._normalizar(func.lower(Store.name)).contains(
                    self._normalizar(func.lower(q))
                )
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(StoreListRow, dict(row)) for row in rows], total

    def _normalizar(self, expr: ColumnElement[str]) -> ColumnElement[str]:
        """Sem acento no Postgres; o SQLite dos testes não tem `unaccent`."""
        if self.db.get_bind().dialect.name == "postgresql":
            return func.immutable_unaccent(expr)
        return expr

    def get_active_products(
        self, store_id: int, params: PageParams
    ) -> tuple[list[Product], int]:
        """Peças ativas daquela loja, paginadas — mais recentes primeiro.

        Pagina manualmente (contagem + offset/limit) em vez de `paginate()`
        genérico: os itens precisam de pós-processamento (`cover_image_url`
        a partir de `images`) que o helper não cobre.
        """
        stmt = (
            select(Product)
            .options(selectinload(Product.images))
            .where(Product.store_id == store_id, Product.status == "ativo")
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = self.db.scalars(stmt.offset(params.offset).limit(params.limit)).all()
        return list(rows), total

    def get_by_user_id(self, user_id: int) -> Store | None:
        return (
            self.db.query(Store)
            .join(Seller, Store.seller_id == Seller.id)
            .filter(Seller.user_id == user_id)
            .first()
        )

    def get_seller_by_user_id(self, user_id: int) -> Seller | None:
        return self.db.query(Seller).filter(Seller.user_id == user_id).first()

    def get_seller_by_document_value(self, document_value: str) -> Seller | None:
        return (
            self.db.query(Seller)
            .filter(Seller.document_value == document_value)
            .first()
        )

    def save(self, store: Store) -> Store:
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)
        return store
