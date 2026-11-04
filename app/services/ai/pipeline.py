"""Processamento e persistência das tarefas de análise de imagens."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.database import SessionLocal
from app.models.product import Product
from app.services.ai.base import AIProviderError, ImageAnalysisProvider
from app.services.ai.worker_factory import get_image_analysis_provider

logger = logging.getLogger("vintex.ai.pipeline")


def process_image_analysis(
    product_id: int,
    image_urls: Sequence[str],
    provider: ImageAnalysisProvider | None = None,
) -> bool:
    """Processa uma tarefa; retorna falso para permitir retry pela fila.

    Falhas do provedor deixam `ai_status=failed`, mas a mensagem não deve ser
    apagada: o SQS aplica retry e encaminha a tarefa à DLQ após três entregas.
    Uma peça já concluída é tratada como sucesso para tolerar entrega duplicada.
    """
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product is None:
            logger.error("Peça %s não encontrada para análise de IA", product_id)
            return True
        if product.ai_status == "done":
            return True

        logger.info("Iniciando análise de IA da peça %s", product_id)
        product.ai_status = "processing"
        product.ai_error = None
        db.commit()

        try:
            result = (provider or get_image_analysis_provider()).analyze_image(
                image_urls
            )
        except Exception as exc:
            logger.warning(
                "Falha na análise de IA da peça %s (%s)",
                product_id,
                type(exc).__name__,
            )
            product.ai_status = "failed"
            product.ai_error = (
                "Provedor de IA indisponível ou falhou na análise."
                if isinstance(exc, AIProviderError)
                else "Falha inesperada na análise de IA."
            )
            db.commit()
            return False

        product.ai_status = "done"
        product.ai_suggestions = result.model_dump(mode="json")
        product.ai_error = None
        db.commit()
        logger.info("Análise de IA da peça %s concluída", product_id)
        return True
    finally:
        db.close()
