"""Seed da versão v0 dos termos de uso e do contrato de venda.

Uso::

    python -m app.seeds.legal

Idempotente: cada documento só é criado se o par (tipo, versão) ainda não
existir. O texto é provisório até a stakeholder enviar o oficial, que entra
como uma versão nova (v1) — nunca editando a v0.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.database import SessionLocal
from app.models.legal_document import SELLER_CONTRACT, TERMS_OF_USE, LegalDocument
from app.repositories.legal_document_repository import LegalDocumentRepository

logger = logging.getLogger("vintex.seeds")

VERSION = "v0"

DOCUMENTOS: dict[str, str] = {
    TERMS_OF_USE: (
        "TERMOS DE USO — VERSÃO PROVISÓRIA (v0)\n\n"
        "Este texto é provisório e será substituído pela versão oficial "
        "fornecida pela Vintex."
    ),
    SELLER_CONTRACT: (
        "CONTRATO DE VENDA — VERSÃO PROVISÓRIA (v0)\n\n"
        "Este texto é provisório e será substituído pela versão oficial "
        "fornecida pela Vintex."
    ),
}


def seed_legal(session: Session) -> int:
    """Cria a v0 dos documentos que ainda não existem. Não faz commit.

    Retorna quantos documentos foram criados.
    """
    repository = LegalDocumentRepository(session)
    created = 0
    for document_type, content in DOCUMENTOS.items():
        if repository.exists(document_type, VERSION):
            continue
        session.add(
            LegalDocument(
                document_type=document_type,
                version=VERSION,
                content=content,
                published_at=utcnow_naive(),
            )
        )
        created += 1

    session.flush()
    return created


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        created = seed_legal(session)
        session.commit()
        logger.info("Documentos jurídicos criados: %d.", created)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
