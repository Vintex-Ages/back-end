from datetime import date

from sqlalchemy import CheckConstraint, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class AIChatUsage(BaseModel):
    """Perguntas feitas ao chat por dia, por chave (back-end#258).

    Uma linha por (dia, chave): a pessoa (`user:<id>` logada, `ip:<origem>`
    visitante) ou o projeto inteiro (`projeto`). É a contagem da cota da busca
    conversacional, e fica no banco para sobreviver a reinício e valer com mais
    de uma requisição ao mesmo tempo. O dia é UTC, como todo datetime do
    projeto.
    """

    __tablename__ = "ai_chat_usage"
    __table_args__ = (
        UniqueConstraint("day", "key", name="uq_ai_chat_usage_day_key"),
        CheckConstraint("count >= 0", name="ck_ai_chat_usage_count"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
