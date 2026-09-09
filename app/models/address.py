from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.store import Store
    from app.models.user import User


class Address(BaseModel):
    __tablename__ = "addresses"
    __table_args__ = (
        Index("ix_addresses_city", "city"),
        Index("ix_addresses_state", "state"),
    )

    street: Mapped[str] = mapped_column(String(150), nullable=False)
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    complement: Mapped[Optional[str]] = mapped_column(String(100))
    neighborhood: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    users: Mapped[List["User"]] = relationship(back_populates="address")
    stores: Mapped[List["Store"]] = relationship(back_populates="address")
