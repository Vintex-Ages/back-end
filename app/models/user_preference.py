from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class UserPreference(BaseModel):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "type",
            "value",
            name="uq_user_preferences_user_type_value",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped["User"] = relationship()
