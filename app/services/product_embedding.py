"""Vetor da peça para a busca por semelhança (back-end#245).

Antes, só o `scripts/backfill_embeddings.py` gravava `Product.embedding`, à
mão: a peça que o vendedor publicava ficava fora do chat e da recomendação, sem
erro nenhum. Agora a publicação grava o vetor, e o backfill fica para o
catálogo antigo e para o que falhou.

O texto que vira vetor é um só, aqui, para a publicação e o backfill gerarem
vetores comparáveis.
"""

from __future__ import annotations

import logging

from app.models.product import Product
from app.services.ai import (
    AIProviderError,
    AIProviderUnavailableError,
    get_ai_provider,
    modelo_de_embedding,
)

logger = logging.getLogger(__name__)

# Os atributos que entram no texto do vetor. Editar um deles regrava o vetor.
CAMPOS_DO_TEXTO = ("name", "description", "brand", "color", "size", "style")


def texto_da_peca(product: Product) -> str:
    valores = (getattr(product, campo) for campo in CAMPOS_DO_TEXTO)
    return " ".join(valor for valor in valores if valor)


def precisa_de_embedding(product: Product) -> bool:
    """Sem vetor, ou com vetor de outro modelo: o mesmo critério do backfill."""
    try:
        modelo = modelo_de_embedding()
    except AIProviderError:
        return True
    return product.embedding is None or product.embedding_model != modelo


def gravar_embedding(product: Product) -> bool:
    """Gera e põe o vetor na peça, sem commit. Devolve se conseguiu.

    Falha da IA não bloqueia o cadastro (RN-57): a peça fica sem vetor, e o
    motivo vai para o log. Sem vetor, o backfill a encontra depois; um vetor
    antigo mantido aqui não seria encontrado, e descreveria a peça de antes.
    """
    try:
        modelo = modelo_de_embedding()
        vetores = get_ai_provider().embed([texto_da_peca(product)])
        if len(vetores) != 1:
            raise AIProviderError(
                f"O provedor devolveu {len(vetores)} vetores para 1 texto."
            )
    except AIProviderUnavailableError:
        # Ambiente sem IA configurada (como a staging hoje): esperado, não alarme.
        logger.info("Peça %s sem vetor: nenhum provedor de IA configurado.", product.id)
        apagar_embedding(product)
        return False
    except Exception:  # noqa: BLE001 - IA é complementar: nada aqui bloqueia a peça
        logger.warning("Peça %s ficou sem vetor de busca.", product.id, exc_info=True)
        apagar_embedding(product)
        return False

    product.embedding = vetores[0]
    product.embedding_model = modelo
    return True


def apagar_embedding(product: Product) -> None:
    """Tira o vetor que não descreve mais a peça. O backfill gera de novo."""
    product.embedding = None
    product.embedding_model = None
