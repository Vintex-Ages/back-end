"""Controller da loja.

Junta os dois lados que nasceram em issues separadas: a loja publica
(back-end#142) e a loja do proprio vendedor (back-end#141). Ficam na mesma
classe porque operam a mesma entidade e o mesmo repositorio.
"""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, NotFound
from app.core.pagination import Page, PageParams
from app.models.address import Address
from app.models.seller import Seller
from app.models.store import Store
from app.repositories.store_repository import StoreRepository
from app.schemas.store_schema import (
    StoreAddressResponse,
    StoreCreate,
    StoreDetailResponse,
    StoreMetricsResponse,
    StoreProductItemResponse,
    StoreResponse,
)


class StoreController:
    def __init__(self, db: Session):
        self.db = db
        self.repository = StoreRepository(db)

    def create(self, user_id: int, data: StoreCreate) -> StoreResponse:
        if self.repository.get_by_user_id(user_id) is not None:
            raise Conflict(
                "O usuário já possui uma loja.", code=ErrorCode.STORE_ALREADY_EXISTS
            )

        document_owner = self.repository.get_seller_by_document_value(
            data.document_value
        )
        if document_owner is not None and document_owner.user_id != user_id:
            raise Conflict(
                "Este documento já está cadastrado para outro vendedor.",
                code=ErrorCode.DOCUMENT_ALREADY_REGISTERED,
            )

        # Data de aceite só existe se houve aceite. A #216 tornou
        # `terms_version` opcional com o argumento de que gravar versão
        # chumbada registraria um aceite que ninguém deu — e deixou o carimbo
        # de data saindo do mesmo jeito, que é a mesma mentira pelo outro lado:
        # um campo jurídico com a data de um aceite sem versão.
        aceito_em = datetime.now(timezone.utc) if data.terms_version else None

        try:
            seller = self.repository.get_seller_by_user_id(user_id)
            if seller is None:
                seller = Seller(
                    user_id=user_id,
                    document_type=data.document_type,
                    document_value=data.document_value,
                    terms_version=data.terms_version,
                    terms_accepted_at=aceito_em,
                )
                self.db.add(seller)
                self.db.flush()
            else:
                seller.document_type = data.document_type
                seller.document_value = data.document_value
                # Vendedor que já aceitou não perde o registro por reenviar o
                # cadastro sem a versão: só sobrescreve quando vem aceite novo.
                if data.terms_version:
                    seller.terms_version = data.terms_version
                    seller.terms_accepted_at = aceito_em

            # O endereco e opcional (modelagem secao 1.4: `address_id` sem NN),
            # mas quando vem tem que virar linha em `addresses` -- senao o
            # `GET /api/stores/{id}` devolve `address: null` para sempre, que
            # foi o estado ate a #216.
            address_id = None
            if data.address is not None:
                endereco = Address(
                    street=data.address.street,
                    number=data.address.number,
                    complement=data.address.complement,
                    neighborhood=data.address.neighborhood,
                    city=data.address.city,
                    state=data.address.state.upper(),
                    zip_code=data.address.zip_code,
                )
                self.db.add(endereco)
                self.db.flush()
                address_id = endereco.id

            store = Store(
                seller_id=seller.id,
                address_id=address_id,
                name=data.name,
                description=data.description,
                logo_url=str(data.logo_url) if data.logo_url else None,
                pix_key=data.pix_key,
            )
            saved_store = self.repository.save(store)
        except IntegrityError as error:
            # Duplicidade de documento já foi excluída pelo pre-check acima;
            # a causa restante aqui é uma corrida (duplo submit concorrente
            # criando a mesma loja/seller), coberta pelo índice único de
            # `stores.seller_id`.
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

    def get_store(self, store_id: int) -> StoreDetailResponse:
        store = self._get_or_404(store_id)
        metrics = self.repository.get_metrics(store_id)

        address = store.address
        return StoreDetailResponse(
            id=store.id,
            name=store.name,
            description=store.description,
            logo_url=store.logo_url,
            verified=store.seller.verified,
            address=(
                StoreAddressResponse(
                    street=address.street,
                    number=address.number,
                    complement=address.complement,
                    neighborhood=address.neighborhood,
                    city=address.city,
                    state=address.state,
                    zip_code=address.zip_code,
                )
                if address is not None
                else None
            ),
            metrics=StoreMetricsResponse(
                created_at=store.created_at,
                products_listed=metrics["products_listed"],
                products_sold=metrics["products_sold"],
            ),
        )

    def list_products(
        self, store_id: int, params: PageParams
    ) -> Page[StoreProductItemResponse]:
        self._get_or_404(store_id)

        products, total = self.repository.get_active_products(store_id, params)
        items = [
            StoreProductItemResponse(
                id=product.id,
                name=product.name,
                price=product.price,
                cover_image_url=(
                    product.images[0].image_url if product.images else None
                ),
                status=product.status,
            )
            for product in products
        ]
        return Page[StoreProductItemResponse](
            items=items, page=params.page, page_size=params.page_size, total=total
        )

    @staticmethod
    def _to_response(store: Store) -> StoreResponse:
        return StoreResponse(
            id=store.id,
            seller_id=store.seller_id,
            name=store.name,
            description=store.description,
            logo_url=store.logo_url,
            pix_key=store.pix_key,
            document_type=store.seller.document_type,
            document_value=store.seller.document_value,
            terms_version=store.seller.terms_version,
            terms_accepted_at=store.seller.terms_accepted_at,
            address=(
                StoreAddressResponse(
                    street=store.address.street,
                    number=store.address.number,
                    complement=store.address.complement,
                    neighborhood=store.address.neighborhood,
                    city=store.address.city,
                    state=store.address.state,
                    zip_code=store.address.zip_code,
                )
                if store.address is not None
                else None
            ),
        )

    def _get_or_404(self, store_id: int) -> Store:
        store = self.repository.get_by_id(store_id)
        if store is None:
            raise NotFound("Loja não encontrada.", code=ErrorCode.STORE_NOT_FOUND)
        return store
