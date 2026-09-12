from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers.auth_controller import AuthController
from app.core.security import require_auth
from app.database import get_db
from app.models.user import User
from app.schemas.auth_schema import (
    AuthResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)

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


@router.post("/login", response_model=AuthResponse)
def login(
    data: LoginRequest,
    controller: AuthController = Depends(get_controller),
) -> AuthResponse:
    return controller.login(data)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    data: RefreshTokenRequest,
    user: User = Depends(require_auth),
    controller: AuthController = Depends(get_controller),
) -> None:
    controller.logout(user, data.refresh_token)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    data: RefreshTokenRequest,
    controller: AuthController = Depends(get_controller),
) -> AuthResponse:
    return controller.refresh(data.refresh_token)
