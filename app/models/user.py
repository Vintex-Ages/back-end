from datetime import datetime
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
    # Versão dos termos de uso aceita no cadastro (RN-93, back-end#259). Os
    # documentos legais são versionados, e sem isto o projeto registrava que
    # a pessoa aceitou, e não o que ela aceitou. Mesmo par de colunas de
    # `sellers`, que guarda o aceite do cadastro da loja. Nulo para quem se
    # cadastrou antes.
    terms_version: Mapped[Optional[str]] = mapped_column(String(20))
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column()

    address: Mapped[Optional["Address"]] = relationship(back_populates="users")
