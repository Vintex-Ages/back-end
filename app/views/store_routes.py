"""BE-US007-2 (back-end#142): loja pública — dados da loja e peças dela.

Rotas públicas, sem login. `/api/users/me/store` (privado, back-end#141) é
outro router — quando aquela issue entrar, é esperado um conflito pequeno em
`app/views/__init__.py` (duas linhas de `include_router`); resolve mantendo
as duas.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.store_controller import StoreController
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.store_schema import StoreDetailResponse, StoreProductItemResponse

router = APIRouter(prefix="/stores", tags=["Stores"])


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
