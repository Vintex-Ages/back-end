import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User

pytestmark = pytest.mark.postgres


def test_unaccent_remove_acentos(pg_session: Session) -> None:
    resultado = pg_session.scalar(select(func.unaccent("Brechó São João")))

    assert resultado == "Brecho Sao Joao"


def test_busca_por_nome_ignora_acento(pg_session: Session) -> None:
    pg_session.add(
        User(name="José Conceição", email="jose@test.local", password_hash="x")
    )
    pg_session.commit()
    termo = "conceicao"

    sem_unaccent = pg_session.scalar(select(User).where(User.name.ilike(f"%{termo}%")))
    com_unaccent = pg_session.scalar(
        select(User).where(func.unaccent(User.name).ilike(func.unaccent(f"%{termo}%")))
    )

    assert sem_unaccent is None
    assert com_unaccent is not None
    assert com_unaccent.name == "José Conceição"


def test_immutable_unaccent_da_migration_esta_disponivel(pg_session: Session) -> None:
    resultado = pg_session.scalar(
        select(func.immutable_unaccent(func.lower("Jaqueta de Couro CLÁSSICA")))
    )

    assert resultado == "jaqueta de couro classica"
