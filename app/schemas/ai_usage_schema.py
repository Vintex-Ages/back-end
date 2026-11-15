"""Consumo do provedor de IA no dia (back-end#263)."""

from datetime import date

from pydantic import BaseModel


class AIUsageGroup(BaseModel):
    """Chamadas de uma funcionalidade ou de um modelo no dia."""

    name: str
    successes: int
    failures: int


class AIUsageResponse(BaseModel):
    """Quanto da cota diária do provedor já foi.

    `remaining` desconta só os sucessos: 503 e 429 são o provedor recusando, e
    não consomem requisição da camada gratuita. As falhas aparecem à parte, e
    `by_model` separa a geração do vetor, que no provedor podem ter limites
    diferentes.
    """

    day: date
    daily_limit: int
    successes: int
    failures: int
    remaining: int
    by_feature: list[AIUsageGroup]
    by_model: list[AIUsageGroup]
