from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, get_args

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.order_item import OrderItem
    from app.models.order_status_history import OrderStatusHistory
    from app.models.payment import Payment
    from app.models.store import Store
    from app.models.user import User

# Os seis estados da RN-82, na ordem do fluxo, mais `expirado`: o pedido sem
# comprovante aprovado em 3 dias sai do fluxo e a peça volta a `ativo`
# (back-end#243). Os nomes são os do contrato do front
# (`front-end/src/types/order.ts`).
#
# O CHECK aceita os sete, mas nem todos viram linha: depois de `confirmado`,
# `preparando`, `enviado` e `concluido` são derivados na leitura a partir da
# data de aprovação (RN-81 e RN-83 simulam postagem e entrega). Eles estão na
# lista para a regra de derivação poder mudar sem migration nova.
OrderStatus = Literal[
    "aguardando_comprovante",
    "em_analise",
    "confirmado",
    "preparando",
    "enviado",
    "concluido",
    "expirado",
]
ORDER_STATUSES: tuple[str, ...] = get_args(OrderStatus)
ORDER_STATUS_CHECK = "status IN ({})".format(
    ", ".join(f"'{status}'" for status in ORDER_STATUSES)
)


class Order(BaseModel):
    """Compra das peças de uma única loja (back-end#243).

    Finalizar um carrinho com N lojas gera N pedidos. A loja fica aqui e é
    repetida em `order_items.store_id`, presa por FK composta a
    `(orders.id, orders.store_id)`: é isso que impede, no banco, um item de
    outra loja entrar no pedido. O `UniqueConstraint` em `(id, store_id)` é
    redundante como unicidade (o `id` já é único) e existe só para ser alvo
    dessa FK.

    Os valores são gravados, não calculados na tela: a comissão (RN-11) não
    pode mudar depois da venda, e o comprador vê preço, taxa e total
    discriminados (RN-16). Não há campo de saldo, repasse nem provedor de
    pagamento: o Pix é por fora, direto na chave do vendedor (RN-13, RN-14,
    RN-19 e RN-20).
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(ORDER_STATUS_CHECK, name="ck_orders_status"),
        CheckConstraint(
            "product_amount >= 0 AND platform_fee >= 0 AND total_amount >= 0",
            name="ck_orders_amounts",
        ),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_orders_commission_rate",
        ),
        UniqueConstraint("id", "store_id", name="uq_orders_id_store"),
        Index("ix_orders_buyer_id", "buyer_id"),
        Index("ix_orders_store_id", "store_id"),
        # A rotina de expiração procura `aguardando_comprovante` vencido.
        Index("ix_orders_status_expires_at", "status", "expires_at"),
    )

    buyer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="aguardando_comprovante",
        server_default="aguardando_comprovante",
    )

    # Soma das peças: é o que o comprador paga.
    product_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Percentual da comissão no momento da compra (0.0900 = 9%, RN-11).
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # Comissão em reais, descontada do vendedor.
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Prazo para o comprovante ser aprovado. Vencido, o pedido vai para
    # `expirado` e a peça volta a `ativo`.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Endereço de entrega copiado na compra. É cópia, não FK para
    # `addresses`: o comprador pode mudar o endereço do perfil depois, e o
    # pedido tem que continuar mostrando para onde a peça foi.
    delivery_street: Mapped[str] = mapped_column(String(150), nullable=False)
    delivery_number: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_complement: Mapped[str | None] = mapped_column(String(100))
    delivery_neighborhood: Mapped[str | None] = mapped_column(String(100))
    delivery_city: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(2), nullable=False)
    delivery_zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    buyer: Mapped["User"] = relationship()
    store: Mapped["Store"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", order_by="OrderItem.id"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", order_by="Payment.id"
    )
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", order_by="OrderStatusHistory.id"
    )
