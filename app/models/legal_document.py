from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class LegalDocument(BaseModel):
    """Texto jurídico versionado (termos de uso e contrato de venda).

    Só recebe INSERT: trocar o texto é publicar uma versão nova. Quem aceitou
    uma versão (ex.: `sellers.terms_version`) continua apontando para o texto
    exato que leu.
    """

    __tablename__ = "legal_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('termos_uso', 'contrato_venda')",
            name="ck_legal_documents_document_type",
        ),
        UniqueConstraint(
            "document_type",
            "version",
            name="uq_legal_documents_type_version",
        ),
    )

    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # String(20) casa com `sellers.terms_version`, que guarda este valor.
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(nullable=False)
