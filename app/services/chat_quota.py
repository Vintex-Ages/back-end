"""Cota da busca conversacional (back-end#258).

O provedor de IA roda na camada gratuita: o que acaba não é dinheiro, é
requisição por dia, e o limite é do projeto inteiro. Sem cota, uma pessoa
fazendo 50 perguntas zerava o dia, e o vendedor que fosse cadastrar uma peça
depois recebia falha na análise da foto.

Duas cotas por dia (UTC), configuráveis: por pessoa (`CHAT_QUOTA_PER_PERSON`) e
do projeto (`CHAT_QUOTA_PER_DAY`). O chat continua sem login (RN-65): quem está
logado conta pelo id, o visitante pela origem da requisição. Não segura quem
quiser burlar, e segura o uso normal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import utcnow_naive
from app.repositories.ai_chat_usage_repository import AIChatUsageRepository

CHAVE_DO_PROJETO = "projeto"
# Brasília não tem horário de verão desde 2019: o fuso é fixo.
_BRASILIA = timezone(timedelta(hours=-3), "BRT")


@dataclass
class CotaEsgotada(Exception):
    """A cota acabou. `volta_em` é a meia-noite UTC seguinte, sem fuso."""

    escopo: Literal["pessoa", "projeto"]
    limite: int
    volta_em: datetime
    # O que a cota conta: "perguntas" no chat, "buscas por foto" na busca por
    # imagem (back-end#255). É o mesmo orçamento diário do provedor; só muda
    # o substantivo da mensagem, para ela falar do que a pessoa fez.
    assunto: str = "perguntas"

    @property
    def mensagem(self) -> str:
        volta = self.volta_em.replace(tzinfo=timezone.utc).astimezone(_BRASILIA)
        quando = f"em {volta:%d/%m} às {volta:%H}h (horário de Brasília)"
        if self.escopo == "pessoa":
            return (
                f"Você atingiu o limite de {self.limite} {self.assunto} por dia à "
                f"Vintex. Volta a funcionar {quando}."
            )
        return (
            f"A Vintex atingiu o limite de {self.assunto} do dia para todo mundo. "
            f"Volta a funcionar {quando}."
        )

    @property
    def retry_at(self) -> str:
        return (
            self.volta_em.replace(tzinfo=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )


def chave_da_pessoa(user_id: int | None, origem: str | None) -> str:
    """Logada pelo id; visitante pela origem da requisição."""
    if user_id is not None:
        return f"user:{user_id}"
    return f"ip:{origem or 'desconhecida'}"


class ChatQuota:
    def __init__(self, db: Session):
        self.db = db
        self.uso = AIChatUsageRepository(db)

    def reservar(
        self,
        pessoa: str,
        agora: datetime | None = None,
        *,
        assunto: str = "perguntas",
    ) -> None:
        """Conta uma pergunta para a pessoa e para o projeto, ou levanta
        `CotaEsgotada` sem contar nenhuma das duas.

        `assunto` só muda o substantivo da mensagem: a busca por foto
        (back-end#255) gasta o mesmo orçamento diário do provedor.
        """
        agora = agora or utcnow_naive()
        dia = agora.date()
        volta_em = datetime.combine(dia + timedelta(days=1), time())
        try:
            if not self.uso.consumir(dia, pessoa, settings.CHAT_QUOTA_PER_PERSON):
                raise CotaEsgotada(
                    "pessoa", settings.CHAT_QUOTA_PER_PERSON, volta_em, assunto
                )
            if not self.uso.consumir(
                dia, CHAVE_DO_PROJETO, settings.CHAT_QUOTA_PER_DAY
            ):
                raise CotaEsgotada(
                    "projeto", settings.CHAT_QUOTA_PER_DAY, volta_em, assunto
                )
        except Exception:
            # A da pessoa pode ter somado antes de a do projeto recusar.
            self.db.rollback()
            raise
        self.db.commit()
