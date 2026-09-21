from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.product import Product


class ProductAiCorrection(BaseModel):
    """Registro de uma correção do vendedor sobre uma sugestão da IA.

    Uma linha por campo corrigido, a cada rascunho salvo — histórico, não
    estado atual. É a partir daqui que se mede se a IA está acertando.
    """

    __tablename__ = "product_ai_corrections"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    suggested: Mapped[str | None] = mapped_column(Text)
    final: Mapped[str] = mapped_column(Text, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="ai_corrections")
