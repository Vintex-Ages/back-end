from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Seller(BaseModel):
    __tablename__ = "sellers"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('CPF', 'CNPJ')",
            name="ck_sellers_document_type",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(4), nullable=False)
    document_value: Mapped[str] = mapped_column(String(18), unique=True, nullable=False)
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    terms_version: Mapped[Optional[str]] = mapped_column(String(20))
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column()

    user: Mapped["User"] = relationship()
