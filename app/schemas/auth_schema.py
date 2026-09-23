"""Schemas de credencial — cadastro e login (`/api/auth/*`).

Contrato definido nas issues #77 (cadastro) e #82 (login). `AuthResponse` é
compartilhado pelos dois: o usuário devolvido nunca inclui `password_hash`.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

_PASSWORD_MIN_LENGTH = 8
_NAME_MIN_LENGTH = 2
_NAME_MAX_LENGTH = 120  # acompanha a coluna users.name (String(120))


def _validar_nome(name: str) -> str:
    nome = name.strip()
    # `Field(min_length=...)` sozinho não barra nome só de espaços: "  " tem
    # length 2 e passaria. O strip aqui garante que a checagem de tamanho
    # vale para o conteúdo de verdade, não para espaços em branco.
    if len(nome) < _NAME_MIN_LENGTH:
        raise ValueError(f"O nome deve ter no mínimo {_NAME_MIN_LENGTH} caracteres.")
    return nome


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


def _normalizar_email(email: str) -> str:
    # "Nome@Ex.com" e "nome@ex.com" são o mesmo e-mail: sem isso, unicidade
    # e login divergem silenciosamente por causa da caixa.
    return email.lower()


class RegisterRequest(BaseModel):
    name: str = Field(max_length=_NAME_MAX_LENGTH)
    email: EmailStr
    password: str
    phone: str | None = None

    @field_validator("name")
    @classmethod
    def validar_nome(cls, value: str) -> str:
        return _validar_nome(value)

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: str) -> str:
        return _normalizar_email(value)

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
        return _normalizar_email(value)


class UserIdentity(BaseModel):
    """Campos públicos comuns a qualquer resposta que exponha o usuário.

    Base de `UserPublic` (aqui) e de `MeResponse` (`app/schemas/user_schema.py`)
    — cada uma acrescenta só o que é próprio do seu endpoint, sem duplicar
    id/name/email/is_admin.
    """

    id: int
    name: str
    email: str
    is_admin: bool

    model_config = {"from_attributes": True}


class UserPublic(UserIdentity):
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserPublic
    access_token: str
    token_type: str = "bearer"
