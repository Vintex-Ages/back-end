from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.address import Address


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_cpf_not_null",
            "cpf",
            unique=True,
            postgresql_where=text("cpf IS NOT NULL"),
            sqlite_where=text("cpf IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cpf: Mapped[Optional[str]] = mapped_column(String(14))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    address_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("addresses.id"),
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    address: Mapped[Optional["Address"]] = relationship(back_populates="users")
