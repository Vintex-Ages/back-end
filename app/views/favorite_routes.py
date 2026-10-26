"""Favoritos do comprador (back-end#252).

Recurso do usuário logado — ADR 0001 §4, por isso `/users/me/favorites`. Exige
estar logado (RN-27), não exige ser vendedor. As escritas são `PUT`/`DELETE`
no próprio id da peça, sem corpo nos dois sentidos, e idempotentes.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.favorite_controller import FavoriteController
from app.core.current_user import get_current_user_id
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.product_schema import ProductFeedItemResponse

router = APIRouter(prefix="/users/me/favorites", tags=["Favorites"])


def get_controller(db: Session = Depends(get_db)) -> FavoriteController:
    return FavoriteController(db)


@router.get(
    "",
    response_model=Page[ProductFeedItemResponse],
    summary="Peças favoritadas, mais recente primeiro",
)
def list_favorites(
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: FavoriteController = Depends(get_controller),
) -> Page[ProductFeedItemResponse]:
    return controller.list_favorites(user_id, params)


@router.put(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Favorita a peça",
    responses={404: {"description": "PRODUCT_NOT_FOUND"}},
)
def add_favorite(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: FavoriteController = Depends(get_controller),
) -> None:
    controller.add_favorite(user_id, product_id)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desfavorita a peça",
)
def remove_favorite(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: FavoriteController = Depends(get_controller),
) -> None:
    controller.remove_favorite(user_id, product_id)
