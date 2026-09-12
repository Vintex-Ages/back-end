from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import utcnow_naive
from app.models.base_model import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(BaseModel):
    """Sessão persistente (ADR 0002, decisão 4).

    O token em si nunca é armazenado — só o hash SHA-256 (`token_hash`),
    suficiente para lookup por igualdade sem guardar o segredo em texto
    puro. `revoked_at` é preenchido no logout e na rotação (`/auth/refresh`
    revoga o token usado e emite um par novo). Datas são naive UTC, como
    `created_at`/`updated_at` de `BaseModel`.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column()

    user: Mapped["User"] = relationship()

    @property
    def is_valid(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at > utcnow_naive()
