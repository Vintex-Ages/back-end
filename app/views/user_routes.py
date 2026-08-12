# Exemplo de View/Route — substitua pelo seu domínio
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
