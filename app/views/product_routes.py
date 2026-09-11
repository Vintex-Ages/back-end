from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_schema import FeedResponse

router = APIRouter(prefix="/products", tags=["Products"])


def get_controller(db: Session = Depends(get_db)) -> ProductController:
    return ProductController(db)


@router.get("", response_model=FeedResponse)
def list_products(
    params: PageParams = Depends(page_params),
    sort: Literal["recent"] = Query(
        "recent", description="Ordenação do feed; atualmente apenas recentes."
    ),
    controller: ProductController = Depends(get_controller),
) -> FeedResponse:
    return controller.get_feed(params)
