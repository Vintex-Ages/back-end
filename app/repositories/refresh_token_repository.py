from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self.db.add(refresh_token)
        self.db.flush()
        return refresh_token

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .one_or_none()
        )

    def revoke(self, refresh_token: RefreshToken) -> None:
        refresh_token.revoked_at = utcnow_naive()
        self.db.add(refresh_token)

    def revoke_if_valid(self, token_hash: str) -> RefreshToken | None:
        """Revoga atomicamente só se o token ainda estiver válido.

        A checagem (`is_valid`) e a revogação viviam em dois passos
        separados (`get_by_hash` + `revoke`), sem garantia de atomicidade:
        duas chamadas de `/auth/refresh` concorrentes com o mesmo token
        liam `revoked_at IS NULL` antes de qualquer uma comitar, e as duas
        emitiam um par novo a partir do mesmo token. O `UPDATE ... WHERE
        revoked_at IS NULL AND expires_at > :now` só afeta uma linha
        mesmo sob concorrência — a segunda tentativa não encontra a linha
        (o banco garante isso via lock de linha), então `revoke_if_valid`
        devolve `None` pra ela.
        """
        now = utcnow_naive()
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(RefreshToken)
        )
        return self.db.execute(stmt).scalar_one_or_none()
