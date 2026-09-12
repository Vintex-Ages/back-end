"""Regras de negócio de credencial — cadastro, login, logout (`/api/auth/*`).

Ver `.ai/adr/0002-autenticacao-jwt.md`. Commit fica no controller (ADR 0001
§6) — os repositories só adicionam e dão flush.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, Unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expires_at,
    verify_password_or_dummy,
)
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)

_CREDENCIAIS_INVALIDAS = "E-mail ou senha inválidos."
_SESSAO_INVALIDA = "Sessão inválida ou expirada. Faça login novamente."

_EMAIL_JA_CADASTRADO = "Este e-mail já está cadastrado."


class AuthController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

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
        except IntegrityError:
            # Corrida: outro cadastro com o mesmo e-mail comitou entre o
            # check acima e este ponto. A constraint de unicidade do banco
            # é a garantia de verdade; o check antes é só a resposta rápida
            # no caso comum. `create()` já dá flush (o INSERT com RETURNING
            # roda ali), por isso o try cobre os dois.
            #
            # Assume que EMAIL_TAKEN é a única causa possível: hoje
            # RegisterRequest nunca preenche `cpf` nem `address_id` (as
            # outras colunas com constraint de unicidade/FK em `users`), só
            # `email`. Se o cadastro passar a aceitar CPF ou endereço,
            # revisar este except — outra IntegrityError seria mal
            # reportada como EMAIL_TAKEN.
            self.db.rollback()
            raise Conflict(_EMAIL_JA_CADASTRADO, code=ErrorCode.EMAIL_TAKEN)

        response = self._issue_auth_response(user)
        self.db.commit()
        return response

    def login(self, data: LoginRequest) -> AuthResponse:
        user = self.repository.get_by_email(data.email)
        # verify_password_or_dummy roda o bcrypt mesmo sem usuário (contra
        # um hash fictício) — não vaza por timing se o e-mail existe.
        senha_valida = verify_password_or_dummy(
            data.password, user.password_hash if user is not None else None
        )
        # Mensagem genérica: não revela se o erro foi no e-mail ou na senha.
        if not senha_valida:
            raise Unauthorized(
                _CREDENCIAIS_INVALIDAS, code=ErrorCode.INVALID_CREDENTIALS
            )
        assert user is not None  # senha_valida só é True com user existente
        response = self._issue_auth_response(user)
        self.db.commit()
        return response

    def logout(self, user: User, raw_refresh_token: str) -> None:
        """Revoga o refresh token informado. Idempotente e silencioso.

        Um token que não existe, já revogado ou de outro usuário não gera
        erro — o resultado observável do logout (a sessão não funciona mais)
        já é garantido nesses casos, e o endpoint não deve confirmar ou negar
        a existência de um token que o chamador não comprovou possuir.
        """
        stored = self.refresh_tokens.get_by_hash(hash_refresh_token(raw_refresh_token))
        if (
            stored is not None
            and stored.user_id == user.id
            and stored.revoked_at is None
        ):
            self.refresh_tokens.revoke(stored)
            self.db.commit()

    def refresh(self, raw_refresh_token: str) -> AuthResponse:
        """Rotaciona a sessão: revoga o refresh token usado e emite um par novo.

        `revoke_if_valid` checa e revoga numa única operação atômica no
        banco — duas chamadas concorrentes com o mesmo token nunca revogam
        e emitem par novo as duas (ver `RefreshTokenRepository`).
        """
        stored = self.refresh_tokens.revoke_if_valid(
            hash_refresh_token(raw_refresh_token)
        )
        if stored is None:
            raise Unauthorized(_SESSAO_INVALIDA)

        user = self.repository.get_by_id(stored.user_id)
        if user is None:
            # Linha órfã (usuário apagado sem cascade no refresh token) —
            # caso não deveria acontecer, mas a revogação já aconteceu
            # acima (revoke_if_valid) e precisa ser persistida mesmo assim;
            # sem este commit, o rollback implícito no fechamento da sessão
            # desfaz a revogação e o token "inválido" continuaria utilizável.
            self.db.commit()
            raise Unauthorized(_SESSAO_INVALIDA)

        response = self._issue_auth_response(user)
        self.db.commit()
        return response

    def _issue_auth_response(self, user: User) -> AuthResponse:
        """Monta o `AuthResponse` (emite access + refresh token).

        Não comita: quem chama decide a fronteira de transação (ADR 0001 §6),
        já que o método é reusado em operações com passos anteriores próprios
        (criar usuário, revogar o refresh token antigo).
        """
        access_token = create_access_token(user.id, user.is_admin)

        raw_refresh_token = generate_refresh_token()
        self.refresh_tokens.create(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=refresh_token_expires_at(),
        )

        return AuthResponse(
            user=UserPublic.model_validate(user),
            access_token=access_token,
            refresh_token=raw_refresh_token,
        )
