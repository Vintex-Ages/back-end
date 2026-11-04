from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controllers.order_controller import status_atual
from app.core.clock import utcnow_naive
from app.core.errors import Conflict, ErrorCode, Forbidden, NotFound
from app.models.store_rating import StoreRating
from app.repositories.order_repository import OrderRepository
from app.repositories.store_rating_repository import StoreRatingRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.store_rating_schema import StoreRatingCreate, StoreRatingResponse


class StoreRatingController:
    """O comprador avalia a loja de um pedido entregue (back-end#267).

    Só quem comprou avalia (RN-76): o pedido tem de ser de quem pede, daquela
    loja e já `concluido`. `concluido` é derivado da aprovação, três dias
    depois dela (RN-83 simula a entrega), e é a mesma regra que a tela do
    pedido mostra (`status_atual`).
    """

    def __init__(self, db: Session):
        self.ratings = StoreRatingRepository(db)
        self.orders = OrderRepository(db)
        self.stores = StoreRepository(db)

    def rate(
        self, user_id: int, store_id: int, data: StoreRatingCreate
    ) -> StoreRatingResponse:
        if self.stores.get_by_id(store_id) is None:
            raise NotFound("Loja não encontrada.", code=ErrorCode.STORE_NOT_FOUND)

        # Pedido de outra pessoa, de outra loja, inexistente ou ainda não
        # entregue: a mesma resposta. Uma diferente confirmaria o id do pedido.
        order = self.orders.get_for_buyer(data.order_id, user_id)
        if (
            order is None
            or order.store_id != store_id
            or status_atual(order, utcnow_naive()) != "concluido"
        ):
            raise Forbidden(
                "Só quem recebeu um pedido desta loja pode avaliá-la.",
                code=ErrorCode.RATING_NOT_ALLOWED,
            )

        try:
            rating = self.ratings.add(
                StoreRating(
                    order_id=order.id,
                    store_id=store_id,
                    author_id=user_id,
                    score=data.score,
                )
            )
            self.ratings.commit()
        except IntegrityError:
            # O `UNIQUE` de `order_id`, e não uma consulta antes: dois cliques
            # ao mesmo tempo, só o primeiro grava.
            self.ratings.rollback()
            raise Conflict(
                "Este pedido já foi avaliado.", code=ErrorCode.ALREADY_RATED
            ) from None

        return StoreRatingResponse(
            id=rating.id,
            store_id=rating.store_id,
            order_id=rating.order_id,
            score=rating.score,
            created_at=rating.created_at,
        )
