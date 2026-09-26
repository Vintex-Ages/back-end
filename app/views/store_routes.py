from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.store_controller import StoreController
from app.core.current_user import get_current_user_id
from app.database import get_db
from app.schemas.store_schema import StoreCreate, StoreResponse

router = APIRouter(prefix="/users/me/store", tags=["Store"])


def get_controller(db: Session = Depends(get_db)) -> StoreController:
    return StoreController(db)


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
def create_store(
    data: StoreCreate,
    user_id: int = Depends(get_current_user_id),
    controller: StoreController = Depends(get_controller),
) -> StoreResponse:
    return controller.create(user_id, data)


@router.get("", response_model=StoreResponse)
def get_store(
    user_id: int = Depends(get_current_user_id),
    controller: StoreController = Depends(get_controller),
) -> StoreResponse:
    return controller.get_own_store(user_id)
