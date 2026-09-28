import re

from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound, ValidationError
from app.models.seller import Seller
from app.repositories.seller_repository import SellerRepository
from app.schemas.seller_schema import SellerVerificationResponse

# BE-US007-1: validação simulada — sem consulta a Receita Federal ou órgão
# externo, só confere se o documento já informado ao virar vendedor bate no
# formato esperado (quantidade de dígitos) para o tipo declarado.
_DOCUMENT_DIGITS = {"CPF": 11, "CNPJ": 14}


class SellerController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SellerRepository(db)

    def verify_store(self, user_id: int) -> SellerVerificationResponse:
        seller = self.repository.get_by_user_id(user_id)
        if seller is None:
            raise NotFound(
                "Loja não encontrada para este usuário.", code=ErrorCode.STORE_NOT_FOUND
            )

        if not seller.verified:
            if not self._documento_valido(seller):
                raise ValidationError(
                    "Documento informado não é um CPF/CNPJ válido.",
                    fields={"document_value": "formato inválido para o tipo informado"},
                )
            seller.verified = True
            self.db.commit()

        return SellerVerificationResponse(verified=seller.verified)

    def _documento_valido(self, seller: Seller) -> bool:
        digitos = re.sub(r"\D", "", seller.document_value)
        return len(digitos) == _DOCUMENT_DIGITS.get(seller.document_type, -1)
