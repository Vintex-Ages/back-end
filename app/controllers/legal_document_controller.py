from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound
from app.models.legal_document import SELLER_CONTRACT, TERMS_OF_USE
from app.repositories.legal_document_repository import LegalDocumentRepository
from app.schemas.legal_document_schema import LegalDocumentResponse


class LegalDocumentController:
    def __init__(self, db: Session):
        self.repository = LegalDocumentRepository(db)

    def get_terms(self) -> LegalDocumentResponse:
        return self._get_latest(TERMS_OF_USE)

    def get_seller_contract(self) -> LegalDocumentResponse:
        return self._get_latest(SELLER_CONTRACT)

    def _get_latest(self, document_type: str) -> LegalDocumentResponse:
        document = self.repository.get_latest(document_type)
        if document is None:
            raise NotFound(
                "Documento jurídico não encontrado.",
                code=ErrorCode.LEGAL_DOCUMENT_NOT_FOUND,
            )
        return LegalDocumentResponse.model_validate(document)
