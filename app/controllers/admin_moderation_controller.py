"""Moderação de anúncios pela administradora (back-end#327).

Tirar do ar (RN-80) é despublicar com motivo gravado — o registro que o
vendedor vê na peça dele —, e devolver é o mesmo caminho do `publish` do
vendedor, inclusive a exigência de foto (RN-47). A diferença está em quem pode:
só a administradora mexe na peça de qualquer vendedor (RN-32), e o vendedor não
republica sozinho o que a moderação tirou (RN-80).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.errors import AppError, Conflict, ErrorCode, NotFound, ValidationError
from app.core.pagination import Page, PageParams
from app.models.product import Product
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.admin_moderation_schema import (
    ModeratedProductResponse,
    ModerationAuthor,
    ModerationResponse,
    ModerationStore,
)
from app.services.product_embedding import pedir_embedding, precisa_de_embedding


class AdminModerationController:
    """Suspender, devolver à vitrine e listar as peças Suspensas (back-end#327)."""

    def __init__(
        self,
        db: Session,
        agendar_embedding: Callable[[int], None] | None = None,
    ):
        self.products = ProductRepository(db)
        self.notifications = NotificationRepository(db)
        # Mesmo gancho do `ProductController`: o vetor é gerado depois da
        # resposta, e a devolução à vitrine volta a valer na busca por
        # semelhança (back-end#245).
        self._agendar_embedding = agendar_embedding or (lambda _product_id: None)

    def suspend(self, product_id: int, reason: str, admin: User) -> ModerationResponse:
        """Tira a peça do ar com motivo, data e autor (RN-80).

        Peça `vendido` ou `reservado` responde 409 e não muda de estado: a
        primeira é dinheiro contado (RN-53) e a segunda está num pedido aberto
        (RN-46) — tirar do ar qualquer uma quebra o pedido de alguém. A RN-80
        não abre exceção, então o anúncio inadequado já reservado continua no ar
        até o pedido resolver.

        Suspender de novo atualiza o motivo e a data, sem avisar outra vez: o
        vendedor não precisa de dois avisos da mesma peça.
        """
        product = self._get(product_id)
        self._recusar_em_pedido(product)

        ja_estava = product.moderated_at is not None
        product.status = "despublicado"
        product.moderation_reason = reason
        product.moderated_at = utcnow_naive()
        product.moderated_by_id = admin.id
        if not ja_estava:
            self.notifications.add_moderation(
                user_id=product.store.seller.user_id, product_id=product.id
            )
        self.products.commit()
        return _resposta(product)

    def restore(self, product_id: int, admin: User) -> ModerationResponse:
        """Devolve a peça Suspensa à vitrine (RN-80), com a checagem do `publish`.

        Sem foto, recusa: a `republish` saiu na `#230` justamente por usar o
        sentido `-> ativo` sem esta checagem e pôr peça sem imagem no feed
        público. Aqui é a mesma regra, pelo mesmo motivo.

        Devolver uma peça que não está suspensa é conflito: esta rota não é o
        "publicar" geral da administradora.
        """
        product = self._get(product_id)
        if product.moderated_at is None:
            raise Conflict(
                "Esta peça não está suspensa pela moderação.",
                code=ErrorCode.PRODUCT_NOT_SUSPENDED,
            )
        if not product.images:
            raise ValidationError(
                "Devolver à vitrine exige ao menos uma foto.",
                fields={"images": "A peça precisa de ao menos uma foto para voltar."},
            )

        product.status = "ativo"
        product.moderation_reason = None
        product.moderated_at = None
        product.moderated_by_id = None

        gerar_vetor = precisa_de_embedding(product)
        if gerar_vetor:
            pedir_embedding(product)
        self.products.commit()
        if gerar_vetor:
            self._agendar_embedding(product.id)
        return _resposta(product)

    def list_suspended(self, params: PageParams) -> Page[ModeratedProductResponse]:
        """As peças tiradas do ar pela moderação, mais recente primeiro.

        A lista é de Suspensas, não de todas as `despublicado`: a peça que o
        vendedor pausou não entra, e é por isso que a distinção existe.
        """
        products, total = self.products.list_moderated(params)
        return Page[ModeratedProductResponse](
            items=[_item(product) for product in products],
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def _get(self, product_id: int) -> Product:
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)
        return product

    @staticmethod
    def _recusar_em_pedido(product: Product) -> None:
        """`vendido` e `reservado` não mudam de estado (409)."""
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode ser despublicada.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status == "reservado":
            raise AppError(
                "Peça reservada em um pedido não pode ser despublicada.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
                status_code=409,
            )


def _resposta(product: Product) -> ModerationResponse:
    return ModerationResponse(
        product_id=product.id,
        status=product.status,
        moderation_reason=product.moderation_reason,
        moderated_at=product.moderated_at,
    )


def _item(product: Product) -> ModeratedProductResponse:
    if product.moderated_at is None:
        # Invariante da consulta (`moderated_at IS NOT NULL`): se cair aqui, é
        # defeito de `list_moderated`, e não dado do usuário.
        raise RuntimeError("Peça da lista de Suspensas sem data de moderação.")
    autor = None
    if product.moderated_by is not None:
        autor = ModerationAuthor(
            id=product.moderated_by.id, name=product.moderated_by.name
        )
    return ModeratedProductResponse(
        id=product.id,
        name=product.name,
        price=product.price,
        cover_image_url=product.cover_image_url,
        status=product.status,
        store=ModerationStore(id=product.store.id, name=product.store.name),
        moderation_reason=product.moderation_reason or "",
        moderated_at=product.moderated_at,
        moderated_by=autor,
    )
