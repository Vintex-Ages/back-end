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

from app.database import SessionLocal
from app.models.product import Product
from app.services.ai import AIProviderError, get_ai_provider, modelo_de_embedding
from app.services.product_embedding import texto_da_peca

logger = logging.getLogger("vintex.scripts.backfill_embeddings")

BATCH_SIZE = 10


def run() -> None:
    # Um nome só (back-end#246): é o que vai para `embedding_model` e é por
    # ele que `find_similar` filtra. Lista é recusada antes de tocar o banco.
    model = modelo_de_embedding()
    provider = get_ai_provider()
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
            # O mesmo texto que a publicação usa (back-end#245): vetores comparáveis.
            texts = [texto_da_peca(product) for product in batch]
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
                product.embedding_status = "done"
                product.embedding_error = None
            db.commit()
            logger.info("Lote %s-%s gravado.", start, start + len(batch))
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
