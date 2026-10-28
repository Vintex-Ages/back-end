"""Vetor da peça para a busca por semelhança (back-end#245).

Antes, só o `scripts/backfill_embeddings.py` gravava `Product.embedding`, à
mão: a peça que o vendedor publicava ficava fora do chat e da recomendação, sem
erro nenhum. Agora a publicação pede o vetor, e ele é gerado em segundo plano,
depois da resposta, como a análise da foto. A situação e o erro ficam
registrados na peça (`embedding_status`, `embedding_error`), como `ai_status` e
`ai_error` registram a análise da foto.

O texto que vira vetor é um só, aqui, usado pela publicação e pelo backfill:
os vetores dos dois são comparáveis.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.product import Product
from app.services.ai import (
    AIProviderError,
    AIProviderUnavailableError,
    get_ai_provider,
    modelo_de_embedding,
)
from app.services.ai.base import ImageAnalysisResult

logger = logging.getLogger(__name__)

_FALHA_DO_PROVEDOR = "Provedor de IA indisponível ou falhou ao gerar o vetor."
_SEM_PROVEDOR = "Nenhum provedor de IA configurado para gerar o vetor."


def texto_da_foto(analise: ImageAnalysisResult) -> str:
    """O texto que a foto da busca vira, para o vetor da consulta (#255).

    Só os atributos que a análise leu, na ordem de `texto_da_peca`: é o
    mesmo espaço vetorial, então o texto da consulta precisa parecer com o
    texto de uma peça. Descrição entra porque é o mais perto de um nome;
    preço, cidade e estilo não existem numa foto.

    Vazio quando a IA respondeu e não reconheceu nada — quem chama decide o
    que fazer, porque um vetor de string vazia não significa nada.
    """
    campos = (
        analise.category,
        analise.description,
        analise.brand,
        analise.color,
        analise.size,
        analise.condition,
        analise.composition,
    )
    return " ".join(campo.value for campo in campos if campo and campo.value)


def texto_da_peca(product: Product) -> str:
    """O texto que vira vetor.

    Os atributos da RN-49 (categoria, tamanho, cor, marca, conservação,
    cidade, preço e descrição), mais o nome e o estilo, que o backfill já
    usava: sem o nome, "jaqueta" ficaria de fora do vetor de uma jaqueta.
    A cidade é a do endereço da loja.

    A composição entra no fim (back-end#257): peça sem composição gera o mesmo
    texto de antes, então os vetores já gravados continuam valendo.
    """
    endereco = product.store.address if product.store else None
    partes = [
        product.name,
        product.category,
        product.description,
        product.brand,
        product.color,
        product.size,
        product.condition,
        product.style,
        endereco.city if endereco else None,
        f"R$ {product.price}" if product.price is not None else None,
        product.composition,
    ]
    return " ".join(parte for parte in partes if parte)


def precisa_de_embedding(product: Product) -> bool:
    """Sem vetor, ou com vetor de outro modelo: o mesmo critério do backfill."""
    try:
        modelo = modelo_de_embedding()
    except AIProviderError:
        return True
    return product.embedding is None or product.embedding_model != modelo


def pedir_embedding(product: Product) -> None:
    """Marca a geração como pendente, sem commit. Quem chama agenda
    `gerar_embedding_da_peca` depois do commit."""
    product.embedding_status = "pending"
    product.embedding_error = None


def apagar_embedding(product: Product) -> None:
    """Tira o vetor que não descreve mais a peça, sem commit.

    Sem vetor, o backfill encontra a peça depois. Um vetor antigo mantido
    descreveria a peça de antes da edição, e o backfill não o encontraria.
    """
    product.embedding = None
    product.embedding_model = None
    product.embedding_status = None
    product.embedding_error = None


def gerar_embedding_da_peca(
    product_id: int, session_factory: Callable[[], Session] | None = None
) -> None:
    """Gera e grava o vetor da peça, em segundo plano e com sessão própria.

    Falha da IA não bloqueia nada (RN-57): a peça já foi publicada, fica sem
    vetor, com `embedding_status = failed` e o motivo em `embedding_error`.
    """
    db = (session_factory or SessionLocal)()
    try:
        product = db.get(Product, product_id)
        if product is None:
            logger.warning("Peça %s sumiu antes de gerar o vetor.", product_id)
            return
        _gravar(product)
        db.commit()
    except Exception:  # noqa: BLE001 - segundo plano: nada pode escapar
        db.rollback()
        logger.exception("Falha ao gravar o vetor da peça %s.", product_id)
    finally:
        db.close()


def _gravar(product: Product) -> None:
    try:
        modelo = modelo_de_embedding()
        vetores = get_ai_provider().embed([texto_da_peca(product)])
        if len(vetores) != 1:
            raise AIProviderError(
                f"O provedor devolveu {len(vetores)} vetores para 1 texto."
            )
    except AIProviderUnavailableError:
        # Ambiente sem IA configurada (como a staging hoje): esperado, não alarme.
        logger.info("Peça %s sem vetor: nenhum provedor de IA.", product.id)
        _falhou(product, _SEM_PROVEDOR)
        return
    except Exception:  # noqa: BLE001 - IA é complementar: nada aqui bloqueia a peça
        logger.warning("Peça %s ficou sem vetor de busca.", product.id, exc_info=True)
        _falhou(product, _FALHA_DO_PROVEDOR)
        return

    product.embedding = vetores[0]
    product.embedding_model = modelo
    product.embedding_status = "done"
    product.embedding_error = None


def _falhou(product: Product, motivo: str) -> None:
    product.embedding = None
    product.embedding_model = None
    product.embedding_status = "failed"
    product.embedding_error = motivo
