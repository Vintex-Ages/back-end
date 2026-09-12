"""Schemas de credencial — cadastro e login (`/api/auth/*`).

Contrato definido nas issues #77 (cadastro) e #82 (login). `AuthResponse` é
compartilhado pelos dois: o usuário devolvido nunca inclui `password_hash`.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

_PASSWORD_MIN_LENGTH = 8


def _validar_senha(password: str) -> str:
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"A senha deve ter no mínimo {_PASSWORD_MIN_LENGTH} caracteres."
        )
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("A senha deve conter ao menos uma letra.")
    if not re.search(r"\d", password):
        raise ValueError("A senha deve conter ao menos um número.")
    return password


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        # "Nome@Ex.com" e "nome@ex.com" são o mesmo e-mail: sem isso,
        # unicidade e login divergem silenciosamente por causa da caixa.
        return value.lower()

    @field_validator("password")
    @classmethod
    def validar_senha(cls, value: str) -> str:
        return _validar_senha(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return value.lower()


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserPublic
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Corpo de `/api/auth/logout` e `/api/auth/refresh` — ver ADR 0002."""

    refresh_token: str
