from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utcnow_naive
from app.repositories.ai_call_log_repository import (
    AICallLogRepository,
    ContagemDoDia,
)
from app.schemas.ai_usage_schema import AIUsageGroup, AIUsageResponse


class AIUsageController:
    """Quanto da cota do dia do provedor de IA já foi, e por quem (back-end#263).

    É o número que diz se as cotas do chat (back-end#258) estão certas: sem ele,
    5 por pessoa e 40 por dia não têm medição por trás.
    """

    def __init__(self, db: Session):
        self.repository = AICallLogRepository(db)

    def consumo(self, dia: date | None = None) -> AIUsageResponse:
        """Sem `dia`, o de hoje, em UTC como a cota do provedor e a do chat."""
        dia = dia or utcnow_naive().date()
        por_funcionalidade = self.repository.por_funcionalidade(dia)
        sucessos = sum(g.sucessos for g in por_funcionalidade)
        falhas = sum(g.falhas for g in por_funcionalidade)
        limite = settings.AI_PROVIDER_DAILY_LIMIT
        return AIUsageResponse(
            day=dia,
            daily_limit=limite,
            successes=sucessos,
            failures=falhas,
            remaining=max(limite - sucessos, 0),
            by_feature=_grupos(por_funcionalidade),
            by_model=_grupos(self.repository.por_modelo(dia)),
        )


def _grupos(contagens: list[ContagemDoDia]) -> list[AIUsageGroup]:
    return [
        AIUsageGroup(name=c.nome, successes=c.sucessos, failures=c.falhas)
        for c in contagens
    ]
