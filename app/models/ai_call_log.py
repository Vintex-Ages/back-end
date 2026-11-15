from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel

# Quem pediu a chamada (back-end#263). `nao_informada` é o valor de quem chama
# o provedor sem declarar a funcionalidade: aparece no registro em vez de sumir.
FUNCIONALIDADES = (
    "conversa",
    "cadastro_foto",
    "busca_imagem",
    "recomendacao",
    "publicacao",
    "backfill",
    "nao_informada",
)
OPERACOES = ("gerar", "vetor")


def _lista_sql(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


class AICallLog(BaseModel):
    """Uma chamada ao provedor de IA, só com o que é medida (back-end#263).

    Uma linha por tentativa: quando a cadeia de modelos pula um que deu 503, a
    tentativa recusada fica registrada com o código e a seguinte diz qual
    modelo respondeu. Nunca guarda a pergunta, o prompt nem a descrição da
    peça. O dia da chamada é o `created_at`, em UTC como todo datetime do
    projeto.
    """

    __tablename__ = "ai_call_logs"
    __table_args__ = (
        CheckConstraint(
            f"feature IN ({_lista_sql(FUNCIONALIDADES)})",
            name="ck_ai_call_logs_feature",
        ),
        CheckConstraint(
            f"operation IN ({_lista_sql(OPERACOES)})",
            name="ck_ai_call_logs_operation",
        ),
        CheckConstraint("duration_ms >= 0", name="ck_ai_call_logs_duration"),
        Index("ix_ai_call_logs_created_at", "created_at"),
    )

    feature: Mapped[str] = mapped_column(String(30), nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Código do provedor (503, 429, 400...) ou, sem código, o nome da exceção.
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
