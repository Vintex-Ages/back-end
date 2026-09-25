"""Preenche `Product.embedding` para o catálogo (BE-US027-1, back-end#92).

Uso::

    python -m scripts.backfill_embeddings

Idempotente: só processa peças sem embedding, ou com embedding de um modelo
diferente do configurado (`settings.GOOGLE_EMBEDDING_MODEL`) — rodar de novo
não duplica nem regrava o que já está atualizado. Roda em lotes, então uma
cota estourada no meio não perde o que já foi salvo: a próxima execução
continua de onde parou.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.product import Product
from app.services.ai import AIProviderError, get_ai_provider

logger = logging.getLogger("vintex.scripts.backfill_embeddings")

BATCH_SIZE = 10

_FIELDS = ("name", "description", "brand", "color", "size", "style")


def _build_text(product: Product) -> str:
    values = (getattr(product, field) for field in _FIELDS)
    return " ".join(value for value in values if value)


def run() -> None:
    provider = get_ai_provider()
    model = settings.GOOGLE_EMBEDDING_MODEL
    db = SessionLocal()
    try:
        pending = (
            db.execute(
                select(Product).where(
                    Product.embedding.is_(None) | (Product.embedding_model != model)
                )
            )
            .scalars()
            .all()
        )
        if not pending:
            logger.info("Nenhuma peça pendente de embedding.")
            return

        logger.info("%s peças pendentes de embedding.", len(pending))
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            texts = [_build_text(product) for product in batch]
            try:
                vectors = provider.embed(texts)
            except AIProviderError:
                logger.exception(
                    "Falha ao gerar embedding do lote %s-%s; tentando de novo na "
                    "próxima execução.",
                    start,
                    start + len(batch),
                )
                continue

            for product, vector in zip(batch, vectors, strict=True):
                product.embedding = vector
                product.embedding_model = model
            db.commit()
            logger.info("Lote %s-%s gravado.", start, start + len(batch))
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
