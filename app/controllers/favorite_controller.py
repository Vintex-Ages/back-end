from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.errors import ErrorCode, NotFound
from app.core.pagination import Page, PageParams
from app.repositories.favorite_repository import FavoriteRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import ProductFeedItemResponse


class FavoriteController:
    """Favoritos do comprador (back-end#252, RN-43).

    As duas escritas são idempotentes: a tela não precisa saber o estado
    anterior para agir. Favoritar avisa o anunciante (RN-85, back-end#261),
    uma vez por pessoa e por peça; desfavoritar não avisa nem apaga o aviso.

    Valem as mesmas situações do detalhe público (`ProductController.PUBLICOS`):
    só se favorita o que o detalhe mostra, e a lista mostra o mesmo. Peça
    vendida ou reservada continua, com o `status` dizendo (RN-44). Rascunho e
    despublicada saem da lista, mas a linha fica: se o vendedor republicar, a
    peça volta para os favoritos.
    """

    def __init__(self, db: Session):
        self.db = db
        self.favorites = FavoriteRepository(db)
        self.products = ProductRepository(db)
        self.notifications = NotificationRepository(db)

    def list_favorites(
        self, user_id: int, params: PageParams
    ) -> Page[ProductFeedItemResponse]:
        rows, total = self.favorites.list_for_user(
            user_id, ProductController.PUBLICOS, params
        )
        return Page[ProductFeedItemResponse](
            items=[ProductFeedItemResponse.from_row(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def add_favorite(self, user_id: int, product_id: int) -> None:
        product = self.products.get_detail_by_id(product_id)
        # Rascunho e despublicada respondem como inexistentes, igual ao detalhe.
        if product is None or product.status not in ProductController.PUBLICOS:
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        self.favorites.add(user_id, product_id)
        dono = product.store.seller.user_id
        # O vendedor que favorita a própria peça não é avisado de si mesmo.
        if dono != user_id:
            self.notifications.add_favorite(dono, product_id, actor_id=user_id)
        self.db.commit()

    def remove_favorite(self, user_id: int, product_id: int) -> None:
        """Sem 404: desfavoritar o que não está favoritado, ou uma peça que nem
        existe, responde igual a desfavoritar de verdade."""
        self.favorites.remove(user_id, product_id)
        self.db.commit()
