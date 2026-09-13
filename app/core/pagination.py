"""Paginação compartilhada por página/tamanho.

Contrato (ver `.ai/adr/0001-fundacao-http-kit-api.md`):

- query params: `page` (>= 1, default 1) e `page_size` (1..100, default 20)
- resposta: `{"items": [...], "page": 1, "page_size": 20, "total": 0}`

Uso numa rota::

    @router.get("/products", response_model=Page[ProductItem])
    def list_products(
        params: PageParams = Depends(page_params),
        db: Session = Depends(get_db),
    ) -> Page[ProductItem]:
        stmt = select(Product).where(Product.status == "ativo").order_by(Product.created_at.desc())
        return paginate(db, stmt, params, item_schema=ProductItem)
"""

from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

T = TypeVar("T")


class PageParams(BaseModel):
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: int = Query(1, ge=1, description="Página, começando em 1."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Itens por página (máx. {MAX_PAGE_SIZE}).",
    ),
) -> PageParams:
    """Dependency FastAPI. Valores fora de faixa viram 422 VALIDATION_ERROR."""
    return PageParams(page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


def paginate(
    db: Session,
    stmt: Select[tuple[object, ...]],
    params: PageParams,
    *,
    item_schema: type[BaseModel] | None = None,
) -> Page[object]:
    """Aplica a paginação a `stmt` e devolve um `Page`.

    Faz uma consulta de contagem e uma de dados — nunca uma por linha.
    Se `item_schema` for dado, cada linha é validada nele (`from_attributes`).
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0

    rows: Sequence[object] = db.scalars(
        stmt.offset(params.offset).limit(params.limit)
    ).all()
    items: list[object]
    if item_schema is not None:
        items = [item_schema.model_validate(row) for row in rows]
    else:
        items = list(rows)

    return Page[object](
        items=items,
        page=params.page,
        page_size=params.page_size,
        total=total,
    )
