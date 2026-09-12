"""Regras de negócio de credencial — cadastro, login, logout (`/api/auth/*`).

Ver `.ai/adr/0002-autenticacao-jwt.md`. Commit fica no controller (ADR 0001
§6) — o repository só adiciona e dá flush.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import AuthResponse, RegisterRequest, UserPublic


class AuthController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)

    def register(self, data: RegisterRequest) -> AuthResponse:
        if self.repository.get_by_email(data.email) is not None:
            raise Conflict(
                "Este e-mail já está cadastrado.", code=ErrorCode.EMAIL_TAKEN
            )

        user = User(
            name=data.name,
            email=data.email,
            phone=data.phone,
            password_hash=hash_password(data.password),
        )
        self.repository.create(user)
        self.db.commit()
        self.db.refresh(user)

        token = create_access_token(user.id, user.is_admin)
        return AuthResponse(
            user=UserPublic.model_validate(user),
            access_token=token,
        )
