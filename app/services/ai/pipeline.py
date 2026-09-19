"""Pipeline assíncrono de ingestão de IA (VE-05, back-end#62).

Processa as fotos de uma peça fora da request HTTP de cadastro, usando
`BackgroundTasks` do FastAPI (sem broker externo — ver `.ai/architecture.md`
e a decisão registrada na Sprint 2). Quem cadastra a peça (VS-014,
back-end#33) chama `enqueue_image_analysis` depois de commitar a peça; o
resultado fica em `Product.ai_status`/`ai_suggestions`/`ai_error`, consultável
via `ProductController.get_ai_status`.

Falha do provedor de IA nunca deve derrubar o cadastro manual: a task roda
depois da resposta HTTP já ter sido enviada, então uma `AIProviderError`
aqui só marca a peça como `failed` — não afeta a criação, que já aconteceu.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import BackgroundTasks

from app.database import SessionLocal
from app.models.product import Product
from app.services.ai.base import AIProviderError
from app.services.ai.factory import get_ai_provider

logger = logging.getLogger("vintex.ai.pipeline")


def enqueue_image_analysis(
    background_tasks: BackgroundTasks,
    product: Product,
    image_urls: Sequence[str],
) -> None:
    """Marca a peça como `pending` e agenda a análise em background.

    Não commita: quem chama já está no meio de uma transação de cadastro
    (ADR 0001 — o controller commita). Se não houver fotos, não agenda nada
    e deixa `ai_status` nulo (nenhuma análise foi solicitada).
    """
    if not image_urls:
        return

    product.ai_status = "pending"
    product.ai_error = None
    background_tasks.add_task(_run_image_analysis, product.id, list(image_urls))


def _run_image_analysis(product_id: int, image_urls: list[str]) -> None:
    """Executa a análise em uma sessão própria, fora da sessão da request."""
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product is None:
            logger.error("Peça %s não encontrada para análise de IA", product_id)
            return

        logger.info("Iniciando análise de IA da peça %s", product_id)
        product.ai_status = "processing"
        db.commit()

        try:
            result = get_ai_provider().analyze_image(image_urls)
        except AIProviderError:
            logger.exception("Falha do provedor de IA para a peça %s", product_id)
            product.ai_status = "failed"
            product.ai_error = "Provedor de IA indisponível ou falhou na análise."
            db.commit()
            return

        logger.info("Análise de IA da peça %s concluída", product_id)
        product.ai_status = "done"
        product.ai_suggestions = result.model_dump(mode="json")
        product.ai_error = None
        db.commit()
    finally:
        db.close()
