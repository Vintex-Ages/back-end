"""Autenticação JWT e autorização por papel.

Ver `.ai/adr/0002-autenticacao-jwt.md` para o contrato completo. Resumo:

- Access token JWT (HS256), payload mínimo: `sub` (id do usuário), `is_admin`,
  `exp`. Não existe coluna `role` em `users` — os papéis são compostos:
  comprador é todo usuário, vendedor é derivado de existir linha em `sellers`,
  admin é `users.is_admin`. `is_seller` nunca vai no token: `require_seller`
  resolve por consulta a cada request.
- Senha nunca em texto puro: hash com bcrypt (`passlib`).
- Dependencies expostas para as rotas: `get_current_user`, `require_auth`,
  `require_seller`, `require_admin`, `optional_user`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import Forbidden, Unauthorized
from app.database import get_db
from app.models.seller import Seller
from app.models.user import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# `auto_error=False`: a ausência de header é tratada pelas dependencies abaixo,
# não pelo FastAPI, para manter o envelope de erro padrão (`AUTH_REQUIRED`).
_bearer_scheme = HTTPBearer(auto_error=False)

TOKEN_TYPE_ACCESS = "access"


def hash_password(password: str) -> str:
    """Gera o hash bcrypt gravado em `users.password_hash`."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Compara a senha em texto puro contra o hash armazenado.

    Um hash malformado (ex.: o sentinela `!seed-no-login` dos usuários de seed)
    faz a verificação falhar, nunca levantar exceção.
    """
    try:
        return _pwd_context.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(user_id: int, is_admin: bool) -> str:
    """Emite o access token (expira em `ACCESS_TOKEN_EXPIRE_MINUTES`)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "is_admin": is_admin,
        "type": TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica e valida assinatura/expiração. Levanta `jwt.PyJWTError` se inválido."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def _user_from_token(token: str, db: Session) -> Optional[User]:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    return db.get(User, user_id)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve o usuário autenticado. Sem token ou token inválido -> 401 `AUTH_REQUIRED`."""
    if credentials is None:
        raise Unauthorized("É necessário entrar ou criar conta para esta ação.")
    user = _user_from_token(credentials.credentials, db)
    if user is None:
        raise Unauthorized("É necessário entrar ou criar conta para esta ação.")
    return user


# Alias por legibilidade nas rotas: `require_auth` quando a rota só precisa
# garantir login (não usa o retorno); `get_current_user` quando usa o usuário.
require_auth = get_current_user


def require_seller(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Exige que o usuário autenticado tenha cadastro de vendedor. Senão -> 403 `FORBIDDEN`."""
    is_seller = db.query(Seller).filter(Seller.user_id == user.id).first() is not None
    if not is_seller:
        raise Forbidden("Ação restrita a vendedores.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Exige `is_admin`. Senão -> 403 `FORBIDDEN`."""
    if not user.is_admin:
        raise Forbidden("Ação restrita a administradores.")
    return user


def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve o usuário se houver token válido; caso contrário devolve `None`.

    Nunca levanta erro: sem token, token expirado ou inválido são todos
    tratados como visitante anônimo. Uma rota pública não pode quebrar por
    causa de um `Authorization` velho no header (RN-26).
    """
    if credentials is None:
        return None
    return _user_from_token(credentials.credentials, db)
