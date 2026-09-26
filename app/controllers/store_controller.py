from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, NotFound
from app.models.seller import Seller
from app.models.store import Store
from app.repositories.store_repository import StoreRepository
from app.schemas.store_schema import StoreCreate, StoreResponse


class StoreController:
    def __init__(self, db: Session):
        self.repository = StoreRepository(db)
        self.db = db

    def create(self, user_id: int, data: StoreCreate) -> StoreResponse:
        if self.repository.get_by_user_id(user_id) is not None:
            raise Conflict(
                "O usuário já possui uma loja.", code=ErrorCode.STORE_ALREADY_EXISTS
            )

        try:
            seller = self.repository.get_seller_by_user_id(user_id)
            if seller is None:
                seller = Seller(
                    user_id=user_id,
                    document_type=data.document_type,
                    document_value=data.document_value,
                    terms_version=data.terms_version,
                    terms_accepted_at=datetime.now(timezone.utc),
                )
                self.db.add(seller)
                self.db.flush()
            else:
                seller.document_type = data.document_type
                seller.document_value = data.document_value
                seller.terms_version = data.terms_version
                seller.terms_accepted_at = datetime.now(timezone.utc)

            store = Store(
                seller_id=seller.id,
                name=data.name,
                description=data.description,
                logo_url=str(data.logo_url),
            )
            saved_store = self.repository.save(store)
        except IntegrityError as error:
            self.db.rollback()
            raise Conflict(
                "Não foi possível criar a loja com os dados informados.",
                code=ErrorCode.STORE_ALREADY_EXISTS,
            ) from error
        return self._to_response(saved_store)

    def get_own_store(self, user_id: int) -> StoreResponse:
        store = self.repository.get_by_user_id(user_id)
        if store is None:
            raise NotFound("Loja não encontrada.", code=ErrorCode.STORE_NOT_FOUND)
        return self._to_response(store)

    @staticmethod
    def _to_response(store: Store) -> StoreResponse:
        return StoreResponse(
            id=store.id,
            seller_id=store.seller_id,
            name=store.name,
            description=store.description,
            logo_url=store.logo_url,
            document_type=store.seller.document_type,
            document_value=store.seller.document_value,
            terms_version=store.seller.terms_version,
            terms_accepted_at=store.seller.terms_accepted_at,
        )
