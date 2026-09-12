"""Regras de negócio de credencial — cadastro, login, logout (`/api/auth/*`).

Ver `.ai/adr/0002-autenticacao-jwt.md`. Commit fica no controller (ADR 0001
§6) — o repository só adiciona e dá flush.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, Unauthorized
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)

_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."

_EMAIL_JA_CADASTRADO = "Este e-mail já está cadastrado."


class AuthController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)

    def register(self, data: RegisterRequest) -> AuthResponse:
        if self.repository.get_by_email(data.email) is not None:
            raise Conflict(_EMAIL_JA_CADASTRADO, code=ErrorCode.EMAIL_TAKEN)

        user = User(
            name=data.name,
            email=data.email,
            phone=data.phone,
            password_hash=hash_password(data.password),
        )
        try:
            self.repository.create(user)
            self.db.commit()
        except IntegrityError:
            # Corrida: outro cadastro com o mesmo e-mail comitou entre o
            # check acima e este ponto. A constraint de unicidade do banco
            # é a garantia de verdade; o check antes é só a resposta rápida
            # no caso comum. `create()` já dá flush (o INSERT com RETURNING
            # roda ali, não só no commit), por isso o try cobre os dois.
            self.db.rollback()
            raise Conflict(_EMAIL_JA_CADASTRADO, code=ErrorCode.EMAIL_TAKEN)

        return self._issue_auth_response(user)

    def login(self, data: LoginRequest) -> AuthResponse:
        user = self.repository.get_by_email(data.email)
        # Mensagem genérica: não revela se o erro foi no e-mail ou na senha.
        if user is None or not verify_password(data.password, user.password_hash):
            raise Unauthorized(
                _CREDENCIAIS_INVALIDAS, code=ErrorCode.INVALID_CREDENTIALS
            )
        return self._issue_auth_response(user)

    def _issue_auth_response(self, user: User) -> AuthResponse:
        token = create_access_token(user.id, user.is_admin)
        return AuthResponse(
            user=UserPublic.model_validate(user),
            access_token=token,
        )
