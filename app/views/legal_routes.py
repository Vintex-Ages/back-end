from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.legal_document_controller import LegalDocumentController
from app.database import get_db
from app.schemas.legal_document_schema import LegalDocumentResponse

# Rotas públicas: o texto precisa ser lido antes do cadastro/login.
router = APIRouter(prefix="/legal", tags=["Legal"])


def get_controller(db: Session = Depends(get_db)) -> LegalDocumentController:
    return LegalDocumentController(db)


@router.get("/terms", response_model=LegalDocumentResponse)
def get_terms(
    controller: LegalDocumentController = Depends(get_controller),
) -> LegalDocumentResponse:
    return controller.get_terms()


@router.get("/seller-contract", response_model=LegalDocumentResponse)
def get_seller_contract(
    controller: LegalDocumentController = Depends(get_controller),
) -> LegalDocumentResponse:
    return controller.get_seller_contract()
