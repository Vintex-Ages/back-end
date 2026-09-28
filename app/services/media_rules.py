"""Regras de formato e tamanho da mídia do produto (VE-04, back-end#73).

O `MediaStorage` (VE-16) trata objeto: sobe bytes, lê bytes, remove. Ele diz na
própria docstring que formato, tamanho e URL não são dele. É o que mora aqui.

Os limites são de propósito iguais aos que `GoogleAIProvider.analyze_image`
aplica ao baixar a foto: se o upload aceitasse um arquivo que a IA depois
recusa, o vendedor só descobriria o problema na etapa da sugestão, com a peça
já meio cadastrada.
"""

from __future__ import annotations

from app.core.errors import ValidationError
from app.services.media_storage import MediaKind

# Mesmo conjunto de `app/services/ai/google.py`. HEIC entra porque iPhone
# fotografa nele por padrão, e a IA aceita.
ALLOWED_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic"})
ALLOWED_VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime"})

MAX_BYTES_PER_FILE = 8 * 1024 * 1024
MAX_BYTES_PER_REQUEST = 24 * 1024 * 1024

# Igual ao `max_length` de `ListingSuggestionsRequest`: as fotos que sobem numa
# peça são as mesmas que vão para a análise.
MAX_FILES_PER_REQUEST = 8

_ALLOWED_BY_KIND: dict[MediaKind, frozenset[str]] = {
    "photo": ALLOWED_PHOTO_TYPES,
    "video": ALLOWED_VIDEO_TYPES,
    "receipt": ALLOWED_PHOTO_TYPES,
    "logo": ALLOWED_PHOTO_TYPES,
}

# Prefixos que a rota pública de leitura pode servir. `payments/receipts/` fica
# fora: comprovante de PIX é documento de uma transação entre duas pessoas, e
# uma chave sorteada não é controle de acesso. Quando houver tela de pedido,
# entra por rota autenticada.
# `logo` entra: a imagem da loja aparece na vitrine pública, igual a foto de
# peça. `payments/receipts/` continua fora.
PUBLIC_KINDS: frozenset[MediaKind] = frozenset({"photo", "video", "logo"})


def validar_tipo(kind: MediaKind, content_type: str | None) -> str:
    permitidos = _ALLOWED_BY_KIND[kind]
    tipo = (content_type or "").split(";")[0].strip().lower()
    if tipo not in permitidos:
        raise ValidationError(
            f"Tipo de arquivo não aceito: {tipo or 'desconhecido'}. "
            f"Aceitos: {', '.join(sorted(permitidos))}.",
        )
    return tipo


def validar_tamanho(nome: str, tamanho: int, total_acumulado: int) -> None:
    if tamanho == 0:
        raise ValidationError(f"Arquivo vazio: {nome}.")
    if tamanho > MAX_BYTES_PER_FILE:
        raise ValidationError(
            f"{nome} passa do limite de {MAX_BYTES_PER_FILE // (1024 * 1024)}MiB por arquivo.",
        )
    if total_acumulado > MAX_BYTES_PER_REQUEST:
        raise ValidationError(
            f"O envio passa do limite de {MAX_BYTES_PER_REQUEST // (1024 * 1024)}MiB somando os arquivos.",
        )


def validar_quantidade(quantidade: int) -> None:
    if quantidade == 0:
        raise ValidationError("Envie ao menos um arquivo.")
    if quantidade > MAX_FILES_PER_REQUEST:
        raise ValidationError(
            f"No máximo {MAX_FILES_PER_REQUEST} arquivos por envio.",
        )
