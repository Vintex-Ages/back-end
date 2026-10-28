from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.ai_chat_usage import AIChatUsage


class AIChatUsageRepository:
    """Contagem diária do chat (back-end#258)."""

    def __init__(self, db: Session):
        self.db = db

    def consumir(self, dia: date, chave: str, limite: int) -> bool:
        """Soma 1 à contagem do dia, se ela ainda não chegou ao limite.

        Devolve se somou. Conferir e somar no mesmo comando (`INSERT ... ON
        CONFLICT DO UPDATE ... WHERE`): duas perguntas ao mesmo tempo na última
        vaga, só uma soma. Sem commit.
        """
        if limite < 1:
            return False
        insert = (
            pg_insert
            if self.db.get_bind().dialect.name == "postgresql"
            else sqlite_insert
        )
        stmt = (
            insert(AIChatUsage)
            .values(day=dia, key=chave, count=1)
            .on_conflict_do_update(
                index_elements=["day", "key"],
                set_={"count": AIChatUsage.count + 1, "updated_at": func.now()},
                where=AIChatUsage.count < limite,
            )
            .returning(AIChatUsage.count)
        )
        return self.db.scalar(stmt) is not None

    def contagem(self, dia: date, chave: str) -> int:
        linha = self.db.scalar(
            select(AIChatUsage.count).where(
                AIChatUsage.day == dia, AIChatUsage.key == chave
            )
        )
        return linha or 0
