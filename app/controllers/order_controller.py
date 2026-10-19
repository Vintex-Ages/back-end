from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.comissao import COMISSAO_VINTEX, dividir
from app.core.errors import Conflict, ErrorCode
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.product import Product
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.order_schema import (
    DeliveryAddress,
    OrderCreate,
    OrderHistoryResponse,
    OrderItemResponse,
    OrderResponse,
    OrderStoreResponse,
)

# Prazo para o comprovante ser aprovado. Vencido, o pedido expira e a peça
# volta a `ativo` (back-end#243).
_PRAZO_DO_COMPROVANTE = timedelta(days=3)
_STATUS_INICIAL = "aguardando_comprovante"


class OrderController:
    """Criação do pedido a partir das peças de uma loja (back-end#247).

    Um pedido é de uma loja só: o comprador paga o preço cheio direto na chave
    Pix do vendedor (RN-19 e RN-20), então cada loja vira um pedido. A
    comissão de 9% (RN-11) sai do lado do vendedor: `platform_fee` é
    informação, e `total_amount` é igual a `product_amount`.

    O pedido nasce em `aguardando_comprovante` e nada aqui o avança (RN-21).
    """

    def __init__(self, db: Session):
        self.orders = OrderRepository(db)
        self.products = ProductRepository(db)

    def create(self, user_id: int, data: OrderCreate) -> OrderResponse:
        products = self.products.get_many_for_order(data.product_ids)
        # Id que não existe responde igual a peça fora de venda: para quem
        # compra, as duas são "esta peça não está disponível".
        if len(products) != len(data.product_ids) or any(
            product.status != "ativo" for product in products
        ):
            raise self._indisponivel()

        if len({product.store_id for product in products}) > 1:
            raise Conflict(
                "Um pedido só pode ter peças de uma loja.",
                code=ErrorCode.MIXED_STORES,
            )

        store = products[0].store
        if not store.pix_key:
            # Sem a chave o comprador não tem como pagar: melhor falhar aqui do
            # que gerar um pedido impagável.
            raise Conflict(
                "Esta loja ainda não cadastrou uma chave Pix.",
                code=ErrorCode.STORE_WITHOUT_PIX,
            )

        # A conferência acima só dá a mensagem certa no caso comum. A garantia
        # contra duas pessoas na mesma peça é o UPDATE condicional: se outra
        # compra reservou alguma entre a leitura e aqui, nada é gravado.
        if self.products.reserve(data.product_ids) != len(data.product_ids):
            self.orders.rollback()
            raise self._indisponivel()

        order = self.orders.create(self._novo_pedido(user_id, products, data))
        self.orders.commit()
        return self._to_response(order)

    @staticmethod
    def _indisponivel() -> Conflict:
        return Conflict(
            "Alguma peça do pedido não está mais disponível.",
            code=ErrorCode.PIECE_UNAVAILABLE,
        )

    @staticmethod
    def _novo_pedido(user_id: int, products: list[Product], data: OrderCreate) -> Order:
        bruto = sum((product.price for product in products), Decimal("0"))
        comissao, _ = dividir(bruto)
        endereco = data.delivery_address
        store_id = products[0].store_id
        return Order(
            buyer_id=user_id,
            store_id=store_id,
            status=_STATUS_INICIAL,
            product_amount=bruto,
            commission_rate=COMISSAO_VINTEX,
            platform_fee=comissao,
            total_amount=bruto,
            expires_at=utcnow_naive() + _PRAZO_DO_COMPROVANTE,
            delivery_street=endereco.street,
            delivery_number=endereco.number,
            delivery_complement=endereco.complement,
            delivery_neighborhood=endereco.neighborhood,
            delivery_city=endereco.city,
            delivery_state=endereco.state,
            delivery_zip_code=endereco.zip_code,
            # Nome, preço e capa são cópia: o pedido continua mostrando o que
            # foi comprado mesmo se a peça for editada depois.
            items=[
                OrderItem(
                    store_id=store_id,
                    product_id=product.id,
                    name=product.name,
                    price=product.price,
                    cover_image_url=(
                        product.images[0].image_url if product.images else None
                    ),
                )
                for product in products
            ],
            status_history=[OrderStatusHistory(status=_STATUS_INICIAL)],
        )

    @staticmethod
    def _to_response(order: Order) -> OrderResponse:
        return OrderResponse(
            id=order.id,
            store=OrderStoreResponse(
                id=order.store.id,
                name=order.store.name,
                pix_key=order.store.pix_key or "",
            ),
            items=[
                OrderItemResponse(
                    product_id=item.product_id,
                    name=item.name,
                    price=item.price,
                    cover_image_url=item.cover_image_url,
                )
                for item in order.items
            ],
            product_amount=order.product_amount,
            platform_fee=order.platform_fee,
            total_amount=order.total_amount,
            status=order.status,
            history=[
                OrderHistoryResponse(status=entry.status, at=entry.changed_at)
                for entry in order.status_history
            ],
            delivery_address=DeliveryAddress(
                zip_code=order.delivery_zip_code,
                street=order.delivery_street,
                number=order.delivery_number,
                complement=order.delivery_complement,
                neighborhood=order.delivery_neighborhood,
                city=order.delivery_city,
                state=order.delivery_state,
            ),
            payment=None,
            expires_at=order.expires_at,
            created_at=order.created_at,
        )
