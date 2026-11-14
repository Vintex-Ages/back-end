"""Registro de cada chamada ao provedor de IA (back-end#263).

O provedor gratuito dá 50 requisições por dia para o projeto inteiro, e quatro
telas disputam a mesma chave. Este módulo grava uma linha por chamada (qual
funcionalidade, qual modelo, quanto demorou, se deu certo) para dar para ler
quanto da cota já foi e quem consome mais.

**Quem pediu** vem de um `ContextVar`, e não de um parâmetro de
`get_ai_provider()`. O ponto de entrada de cada funcionalidade declara
`definir_funcionalidade(...)` e o provedor lê na hora de registrar. Cada
requisição roda numa cópia própria do contexto, e `run_in_threadpool` e
`asyncio.to_thread` levam essa cópia para a thread, então o valor chega até a
chamada do SDK sem atravessar as assinaturas do meio. Quem não declarar aparece
como `nao_informada`: o registro mostra o buraco em vez de escondê-lo.

**Registrar é observação, não caminho crítico** (RN-57): grava numa sessão
própria e qualquer falha é logada e engolida. A chamada à IA segue igual.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.repositories.ai_call_log_repository import AICallLogRepository

logger = logging.getLogger(__name__)

Funcionalidade = Literal[
    "conversa",
    "cadastro_foto",
    "busca_imagem",
    "recomendacao",
    "publicacao",
    "backfill",
    "nao_informada",
]
Operacao = Literal["gerar", "vetor"]

_funcionalidade: ContextVar[Funcionalidade] = ContextVar(
    "funcionalidade_de_ia", default="nao_informada"
)

# Trocável nos testes, como o `session_factory` de `gerar_embedding_da_peca`.
session_factory: Callable[[], Session] = SessionLocal


def definir_funcionalidade(nome: Funcionalidade) -> None:
    """Declara quem está chamando a IA no contexto atual.

    Sem `reset` de propósito: o contexto é da requisição (ou da tarefa em
    segundo plano) e morre com ela.
    """
    _funcionalidade.set(nome)


def funcionalidade_atual() -> Funcionalidade:
    return _funcionalidade.get()


def codigo_do_erro(exc: BaseException) -> str:
    """O código do provedor (503, 429, 400...) ou, sem ele, o nome da exceção.

    Nunca a mensagem: ela pode repetir o que foi mandado ao modelo.
    """
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(codigo, int):
        return str(codigo)
    return type(exc).__name__[:40]


def registrar_chamada(
    *,
    operacao: Operacao,
    modelo: str,
    inicio: float,
    erro: BaseException | None = None,
) -> None:
    """Grava uma chamada. `inicio` é o `time.perf_counter()` de antes dela.

    Nunca levanta: falha ao gravar vira log e a chamada segue.
    """
    duracao_ms = max(int((time.perf_counter() - inicio) * 1000), 0)
    try:
        db = session_factory()
        try:
            AICallLogRepository(db).registrar(
                feature=funcionalidade_atual(),
                operation=operacao,
                model=modelo[:80],
                duration_ms=duracao_ms,
                success=erro is None,
                error_code=None if erro is None else codigo_do_erro(erro),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - registro não derruba a chamada (RN-57)
        logger.exception("Falha ao registrar chamada de IA (%s, %s)", operacao, modelo)
