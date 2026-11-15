from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.models.ai_call_log import AICallLog


@dataclass(frozen=True)
class ContagemDoDia:
    """Sucessos e falhas de um grupo (uma funcionalidade ou um modelo)."""

    nome: str
    sucessos: int
    falhas: int


class AICallLogRepository:
    """Registro das chamadas ao provedor de IA (back-end#263)."""

    def __init__(self, db: Session):
        self.db = db

    def registrar(
        self,
        *,
        feature: str,
        operation: str,
        model: str,
        duration_ms: int,
        success: bool,
        error_code: str | None,
    ) -> None:
        """Adiciona a linha, sem commit.

        `created_at` vai explícito em UTC: o padrão do banco (`now()`) segue o
        fuso da sessão no Postgres, e o dia da leitura é contado em UTC.
        """
        self.db.add(
            AICallLog(
                created_at=utcnow_naive(),
                feature=feature,
                operation=operation,
                model=model,
                duration_ms=duration_ms,
                success=success,
                error_code=error_code,
            )
        )

    def por_funcionalidade(self, dia: date) -> list[ContagemDoDia]:
        return self._agrupado(AICallLog.feature, dia)

    def por_modelo(self, dia: date) -> list[ContagemDoDia]:
        return self._agrupado(AICallLog.model, dia)

    def _agrupado(self, coluna, dia: date) -> list[ContagemDoDia]:  # noqa: ANN001
        # Intervalo do dia, e não `func.date(created_at)`: assim o índice em
        # `created_at` serve, e a mesma consulta vale no SQLite e no Postgres.
        inicio = datetime.combine(dia, time.min)
        fim = inicio + timedelta(days=1)
        sucessos = func.sum(case((AICallLog.success.is_(True), 1), else_=0))
        falhas = func.sum(case((AICallLog.success.is_(False), 1), else_=0))
        linhas = self.db.execute(
            select(coluna, sucessos, falhas)
            .where(AICallLog.created_at >= inicio, AICallLog.created_at < fim)
            .group_by(coluna)
            .order_by(coluna)
        ).all()
        return [
            ContagemDoDia(nome=nome, sucessos=int(s or 0), falhas=int(f or 0))
            for nome, s, f in linhas
        ]
