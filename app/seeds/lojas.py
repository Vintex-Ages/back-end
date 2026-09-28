"""Seed de endereços, vendedores e lojas sintéticas do Rio Grande do Sul.

Uso::

    python -m app.seeds.lojas

Idempotente: cada loja é criada só se ainda não existir (busca por nome).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Address, Seller, Store, User

logger = logging.getLogger("vintex.seeds")

# Senha inutilizável — contas de seed não fazem login (auth é da Sprint 2).
_UNUSABLE_PASSWORD = "!seed-no-login"

# nome, cidade, bairro, rua, numero, cep, dono, documento (CNPJ), verificado
LOJAS: list[dict[str, object]] = [
    {
        "nome": "Brechó Mercado Público",
        "cidade": "Porto Alegre",
        "bairro": "Centro Histórico",
        "rua": "Rua Sete de Setembro",
        "numero": "1020",
        "cep": "90010-190",
        "dono": "Marina Oliveira",
        "documento": "12.345.678/0001-01",
        "verificado": True,
    },
    {
        "nome": "Garimpo da Redenção",
        "cidade": "Porto Alegre",
        "bairro": "Bom Fim",
        "rua": "Avenida Osvaldo Aranha",
        "numero": "455",
        "cep": "90035-190",
        "dono": "Rafael Menezes",
        "documento": "12.345.678/0001-02",
        "verificado": True,
    },
    {
        "nome": "Roupa Rodada",
        "cidade": "Caxias do Sul",
        "bairro": "São Pelegrino",
        "rua": "Rua Os Dezoito do Forte",
        "numero": "2100",
        "cep": "95020-472",
        "dono": "Camila Bertuol",
        "documento": "12.345.678/0001-03",
        "verificado": False,
    },
    {
        "nome": "Segunda Chance Modas",
        "cidade": "Pelotas",
        "bairro": "Centro",
        "rua": "Rua Marechal Deodoro",
        "numero": "760",
        "cep": "96020-220",
        "dono": "Júlia Amaral",
        "documento": "12.345.678/0001-04",
        "verificado": True,
    },
    {
        "nome": "Baú da Vó Nair",
        "cidade": "Santa Maria",
        "bairro": "Nossa Senhora do Rosário",
        "rua": "Rua do Acampamento",
        "numero": "380",
        "cep": "97050-001",
        "dono": "Nair Rodrigues",
        "documento": "12.345.678/0001-05",
        "verificado": False,
    },
    {
        "nome": "Desapego Serrano",
        "cidade": "Gramado",
        "bairro": "Centro",
        "rua": "Rua Coberta",
        "numero": "55",
        "cep": "95670-000",
        "dono": "Otávio Lima",
        "documento": "12.345.678/0001-06",
        "verificado": True,
    },
    {
        "nome": "Ateliê Reviver",
        "cidade": "Canoas",
        "bairro": "Centro",
        "rua": "Rua Doutor Barcelos",
        "numero": "1450",
        "cep": "92010-000",
        "dono": "Priscila Fontes",
        "documento": "12.345.678/0001-07",
        "verificado": False,
    },
]


def _slug(nome: str) -> str:
    return (
        nome.lower()
        .replace("ç", "c")
        .replace("ê", "e")
        .replace("ó", "o")
        .replace("á", "a")
        .replace("ã", "a")
        .replace(" ", "-")
    )


def seed_lojas(session: Session) -> list[Store]:
    """Cria as lojas que ainda não existem. Não faz commit."""
    stores: list[Store] = []
    for spec in LOJAS:
        nome = str(spec["nome"])
        existing = session.query(Store).filter_by(name=nome).one_or_none()
        if existing is not None:
            stores.append(existing)
            continue

        slug = _slug(nome)
        address = Address(
            street=str(spec["rua"]),
            number=str(spec["numero"]),
            neighborhood=str(spec["bairro"]),
            city=str(spec["cidade"]),
            state="RS",
            zip_code=str(spec["cep"]),
        )
        user = User(
            name=str(spec["dono"]),
            email=f"seed+{slug}@vintex.local",
            password_hash=_UNUSABLE_PASSWORD,
        )
        seller = Seller(
            user=user,
            document_type="CNPJ",
            document_value=str(spec["documento"]),
            verified=bool(spec["verificado"]),
        )
        store = Store(
            name=nome,
            description=f"Brechó em {spec['cidade']}/RS.",
            pix_key=f"{slug}@vintex.local",
            seller=seller,
            address=address,
        )
        session.add(store)
        stores.append(store)

    session.flush()
    return stores


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        stores = seed_lojas(session)
        session.commit()
        logger.info("Lojas no banco: %d.", len(stores))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
