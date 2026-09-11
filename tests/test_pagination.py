"""Paginação compartilhada (`app/core/pagination.py`)."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.errors import ErrorCode, register_exception_handlers
from app.core.pagination import Page, PageParams, page_params, paginate


class _Base(DeclarativeBase):
    pass


class _Widget(_Base):
    __tablename__ = "widgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class _WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all([_Widget(name=f"w{i:02d}") for i in range(25)])
        sess.commit()
        yield sess


def test_pagina_do_meio_traz_o_recorte_certo(session: Session) -> None:
    stmt = select(_Widget).order_by(_Widget.id)
    result = paginate(session, stmt, PageParams(page=2, page_size=10))

    assert result.total == 25
    assert result.page == 2
    assert len(result.items) == 10
    assert result.items[0].id == 11


def test_ultima_pagina_parcial(session: Session) -> None:
    stmt = select(_Widget).order_by(_Widget.id)
    result = paginate(session, stmt, PageParams(page=3, page_size=10))
    assert len(result.items) == 5


def test_item_schema_valida_as_linhas(session: Session) -> None:
    stmt = select(_Widget).order_by(_Widget.id)
    result = paginate(
        session, stmt, PageParams(page=1, page_size=3), item_schema=_WidgetOut
    )
    assert all(isinstance(item, _WidgetOut) for item in result.items)


def test_conjunto_vazio(session: Session) -> None:
    stmt = select(_Widget).where(_Widget.name == "inexistente")
    result = paginate(session, stmt, PageParams(page=1, page_size=10))
    assert result.total == 0
    assert result.items == []


# --- a dependency page_params ---


def _params_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/things", response_model=Page[int])
    def _things(params: PageParams = Depends(page_params)) -> Page[int]:
        return Page[int](
            items=[], page=params.page, page_size=params.page_size, total=0
        )

    return app


@pytest.fixture
def params_client() -> TestClient:
    return TestClient(_params_app())


def test_defaults(params_client: TestClient) -> None:
    body = params_client.get("/things").json()
    assert body["page"] == 1 and body["page_size"] == 20


@pytest.mark.parametrize("qs", ["page=0", "page_size=0", "page_size=101", "page=-1"])
def test_valores_fora_de_faixa_viram_422(params_client: TestClient, qs: str) -> None:
    resp = params_client.get(f"/things?{qs}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
