"""Rotas da loja.

Dois routers de proposito, com publicos diferentes:

- `router` (`/api/stores`): publico, sem login — dados da loja e as pecas dela
  (BE-US007-2, back-end#142).
- `me_router` (`/api/users/me/store`): a loja do proprio vendedor, criacao e
  leitura (BE-US006-1, back-end#141). Sob `/users/me/*` pelo ADR 0001 secao 4.

Mesmo arquivo porque e o mesmo recurso; routers separados porque um exige
login e o outro nao pode exigir.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.store_controller import StoreController
from app.core.current_user import get_current_user_id
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.store_schema import (
    StoreCreate,
    StoreDetailResponse,
    StoreProductItemResponse,
    StoreResponse,
)

router = APIRouter(prefix="/stores", tags=["Stores"])
me_router = APIRouter(prefix="/users/me/store", tags=["Store"])


def get_controller(db: Session = Depends(get_db)) -> StoreController:
    return StoreController(db)


@router.get("/{store_id}", response_model=StoreDetailResponse)
def get_store(
    store_id: int,
    controller: StoreController = Depends(get_controller),
) -> StoreDetailResponse:
    return controller.get_store(store_id)


@router.get("/{store_id}/products", response_model=Page[StoreProductItemResponse])
def list_store_products(
    store_id: int,
    params: PageParams = Depends(page_params),
    controller: StoreController = Depends(get_controller),
) -> Page[StoreProductItemResponse]:
    return controller.list_products(store_id, params)


@me_router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
def create_store(
    data: StoreCreate,
    user_id: int = Depends(get_current_user_id),
    controller: StoreController = Depends(get_controller),
) -> StoreResponse:
    return controller.create(user_id, data)


@me_router.get("", response_model=StoreResponse)
def get_own_store(
    user_id: int = Depends(get_current_user_id),
    controller: StoreController = Depends(get_controller),
) -> StoreResponse:
    return controller.get_own_store(user_id)
