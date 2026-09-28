from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.legal_document import LegalDocument


class LegalDocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, document_type: str) -> LegalDocument | None:
        """Versão vigente = a publicada por último daquele tipo.

        Não existe coluna "atual": versões antigas continuam na tabela e a
        vigente sai da ordenação. `id` desempata publicações no mesmo instante.
        """
        return self.db.scalar(
            select(LegalDocument)
            .where(LegalDocument.document_type == document_type)
            .order_by(LegalDocument.published_at.desc(), LegalDocument.id.desc())
            .limit(1)
        )

    def exists(self, document_type: str, version: str) -> bool:
        return (
            self.db.scalar(
                select(LegalDocument.id).where(
                    LegalDocument.document_type == document_type,
                    LegalDocument.version == version,
                )
            )
            is not None
        )
