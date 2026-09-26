"""Regras de negócio de credencial — cadastro, login, logout (`/api/auth/*`).

Ver `.ai/adr/0002-autenticacao-jwt.md`. Commit fica no controller (ADR 0001
§6) — o repository só adiciona e dá flush.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import AuthResponse, RegisterRequest, UserPublic

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
            #
            # Assume que EMAIL_TAKEN é a única causa possível: hoje
            # RegisterRequest nunca preenche `cpf` nem `address_id` (as
            # outras colunas com constraint de unicidade/FK em `users`), só
            # `email`. Se o cadastro passar a aceitar CPF ou endereço,
            # revisar este except — outra IntegrityError seria mal
            # reportada como EMAIL_TAKEN.
            self.db.rollback()
            raise Conflict(_EMAIL_JA_CADASTRADO, code=ErrorCode.EMAIL_TAKEN)

        token = create_access_token(user.id, user.is_admin)
        return AuthResponse(
            user=UserPublic.model_validate(user),
            access_token=token,
        )
