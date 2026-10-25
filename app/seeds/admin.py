"""Seed da conta da administradora (back-end#61).

Uso::

    python -m app.seeds.admin

Na PoC a administradora é a própria stakeholder (RN-25), e é ela quem valida
os comprovantes (RN-21). Diferente das contas de `lojas.py`, esta faz login:
sem ela não há com que conta entrar nas rotas de `/api/admin`.

Idempotente: se a conta já existe, garante o papel e não mexe na senha, para
não desfazer uma troca feita depois do primeiro seed.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import User

logger = logging.getLogger("vintex.seeds")

# Senha de desenvolvimento, documentada no README. Nunca vale em produção.
DEV_ADMIN_PASSWORD = "vintex-admin-dev"


def _senha() -> str:
    if settings.SEED_ADMIN_PASSWORD:
        return settings.SEED_ADMIN_PASSWORD
    if settings.APP_ENV == "production":
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD não configurada. Em produção a conta da "
            "administradora não pode nascer com a senha de desenvolvimento."
        )
    return DEV_ADMIN_PASSWORD


def seed_admin(session: Session) -> User:
    """Cria a administradora, ou garante o papel se ela já existe. Não faz commit."""
    email = settings.SEED_ADMIN_EMAIL
    user = session.query(User).filter_by(email=email).one_or_none()
    if user is None:
        user = User(
            name="Administradora Vintex",
            email=email,
            password_hash=hash_password(_senha()),
            is_admin=True,
        )
        session.add(user)
    else:
        user.is_admin = True

    session.flush()
    return user


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        user = seed_admin(session)
        session.commit()
        logger.info("Administradora no banco: %s.", user.email)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
