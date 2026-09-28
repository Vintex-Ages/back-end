from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    A checagem de validade (não revogado e não expirado) não vive aqui como
    propriedade Python — mora em `RefreshTokenRepository.revoke_if_valid()`,
    como um único `UPDATE ... WHERE` atômico. Um `is_valid` de conveniência
    reintroduziria a race condition que esse método fecha (ler validade e
    revogar em dois passos separados, sem garantia contra concorrência).
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
