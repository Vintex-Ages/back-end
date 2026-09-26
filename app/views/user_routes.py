from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user_controller import UserController
from app.core.current_user import get_current_user_id
from app.database import get_db
from app.schemas.user_schema import UserMeResponse

router = APIRouter(prefix="/users/me", tags=["Users"])


def get_controller(db: Session = Depends(get_db)) -> UserController:
    return UserController(db)


@router.get("", response_model=UserMeResponse)
def get_me(
    user_id: int = Depends(get_current_user_id),
    controller: UserController = Depends(get_controller),
) -> UserMeResponse:
    return controller.get_me(
        user_id
    )  # Exemplo de View/Route — substitua pelo seu domínio


#
# from fastapi import APIRouter, Depends, status
# from sqlalchemy.orm import Session
# from app.controllers.user_controller import UserController
# from app.database import get_db
# from app.schemas.user_schema import UserCreate, UserResponse
#
# router = APIRouter(prefix="/users", tags=["Users"])
#
#
# def get_controller(db: Session = Depends(get_db)) -> UserController:
#     return UserController(db)
#
#
# @router.get("/", response_model=list[UserResponse])
# def list_users(controller: UserController = Depends(get_controller)):
#     return controller.get_all()
#
#
# @router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
# def create_user(data: UserCreate, controller: UserController = Depends(get_controller)):
#     return controller.create(data)
