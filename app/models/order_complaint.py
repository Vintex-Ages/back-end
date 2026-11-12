from typing import Literal, get_args

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.order import Order
from app.models.user import User

# Os dois motivos que a RN-77 nomeia, e só eles.
ComplaintReason = Literal["nao_recebido", "danificado"]
COMPLAINT_REASONS: tuple[str, ...] = get_args(ComplaintReason)
COMPLAINT_REASON_CHECK = "reason IN ({})".format(
    ", ".join(f"'{reason}'" for reason in COMPLAINT_REASONS)
)


class OrderComplaint(BaseModel):
    """Reclamação do comprador sobre um pedido: não recebido ou danificado
    (back-end#268).

    Ao contrário da avaliação da loja, que não tem comentário (RN-75), aqui o
    texto é o conteúdo da reclamação. Ela só chega à administradora e ao
    avaliado (RN-78); nenhuma rota pública a devolve, e a loja e a peça não
    mostram sinal dela. Sem chat direto, a administradora intermedia (RN-79).

    Uma por pedido: o `UNIQUE` em `order_id` é o que garante isso, inclusive
    em dois cliques ao mesmo tempo. O motivo é conferido no schema e de novo
    no CHECK do banco.
    """

    __tablename__ = "order_complaints"
    __table_args__ = (
        CheckConstraint(COMPLAINT_REASON_CHECK, name="ck_order_complaints_reason"),
        Index("uq_order_complaints_order_id", "order_id", unique=True),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    order: Mapped[Order] = relationship()
    author: Mapped[User] = relationship()
