from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.auth_controller import AuthController
from app.database import get_db
from app.schemas.auth_schema import AuthResponse, RegisterRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_controller(db: Session = Depends(get_db)) -> AuthController:
    return AuthController(db)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    controller: AuthController = Depends(get_controller),
) -> AuthResponse:
    return controller.register(data)
