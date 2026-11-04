"""Regras de formato e tamanho da mídia do produto (VE-04, back-end#73).

O `MediaStorage` (VE-16) trata objeto: sobe bytes, lê bytes, remove. Ele diz na
própria docstring que formato, tamanho e URL não são dele. É o que mora aqui.

Os limites são de propósito iguais aos que `GoogleAIProvider.analyze_image`
aplica ao baixar a foto: se o upload aceitasse um arquivo que a IA depois
recusa, o vendedor só descobriria o problema na etapa da sugestão, com a peça
já meio cadastrada.
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from app.core.errors import ValidationError
from app.services.media_storage import MEDIA_PREFIXES, MediaKind
from app.services.video_duration import DuracaoIlegivel, duracao_em_segundos

# Mesmo conjunto de `app/services/ai/google.py`. HEIC entra porque iPhone
# fotografa nele por padrão, e a IA aceita.
ALLOWED_PHOTO_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic"})
ALLOWED_VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime"})
# Comprovante é imagem ou PDF (RN-20): o print do app do banco ou o PDF que o
# próprio banco gera (back-end#244). PDF só aqui; foto de peça continua imagem.
ALLOWED_RECEIPT_TYPES = ALLOWED_PHOTO_TYPES | {"application/pdf"}

MAX_BYTES_PER_FILE = 8 * 1024 * 1024
MAX_BYTES_PER_REQUEST = 24 * 1024 * 1024

# Igual ao `max_length` de `ListingSuggestionsRequest`: as fotos que sobem numa
# peça são as mesmas que vão para a análise.
MAX_FILES_PER_REQUEST = 8

# Vídeo curto de 3 a 5 segundos no anúncio (RN-48, back-end#270).
MIN_VIDEO_SECONDS = 3.0
MAX_VIDEO_SECONDS = 5.0

_ALLOWED_BY_KIND: dict[MediaKind, frozenset[str]] = {
    "photo": ALLOWED_PHOTO_TYPES,
    "video": ALLOWED_VIDEO_TYPES,
    "receipt": ALLOWED_RECEIPT_TYPES,
    "logo": ALLOWED_PHOTO_TYPES,
    # A etiqueta vai para a mesma análise das fotos, então aceita o mesmo.
    "label": ALLOWED_PHOTO_TYPES,
}

# Prefixos que a rota pública de leitura pode servir. `payments/receipts/` fica
# fora: comprovante de PIX é documento de uma transação entre duas pessoas, e
# uma chave sorteada não é controle de acesso. Quem abre o arquivo é só a
# administradora, por `GET /api/admin/payments/{order_id}/receipt`
# (back-end#244).
# `logo` entra: a imagem da loja aparece na vitrine pública, igual a foto de
# peça. `payments/receipts/` continua fora.
# `label` entra porque é por esta rota que o servidor baixa a foto para a IA
# (back-end#257), e uma etiqueta de roupa não tem nada de sigiloso. Ficar fora
# da galeria é outra regra: a peça recusa essa URL em `images`
# (`e_foto_de_etiqueta`).
PUBLIC_KINDS: frozenset[MediaKind] = frozenset({"photo", "video", "logo", "label"})

_CAMINHO_DA_ETIQUETA = f"/api/media/{MEDIA_PREFIXES['label']}"
_CAMINHO_DO_VIDEO = f"/api/media/{MEDIA_PREFIXES['video']}"


def _caminho(url: str) -> str | None:
    """Só o caminho, depois de decodificado: a origem muda por ambiente
    (`PUBLIC_BASE_URL`), o caminho da mídia não."""
    try:
        return unquote(urlsplit(url).path)
    except ValueError:
        return None


def e_foto_de_etiqueta(url: str) -> bool:
    """A URL aponta para uma foto de etiqueta subida por `/api/users/me/media`."""
    caminho = _caminho(url)
    return caminho is not None and _CAMINHO_DA_ETIQUETA in caminho


def e_video(url: str) -> bool:
    """A URL aponta para um vídeo subido por `/api/users/me/media`
    (back-end#270)."""
    caminho = _caminho(url)
    return caminho is not None and _CAMINHO_DO_VIDEO in caminho


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


def validar_duracao_do_video(nome: str, conteudo: bytes) -> None:
    """Recusa vídeo fora de 3 a 5 segundos (RN-48), dizendo a duração
    recebida (o critério da #219).

    Compara com uma casa decimal: o celular grava "5 segundos" como 5,03, e
    recusar isso seria recusar o que a pessoa acabou de fazer certo.
    """
    try:
        segundos = duracao_em_segundos(conteudo)
    except DuracaoIlegivel:
        raise ValidationError(
            f"Não foi possível ler a duração de {nome}. Envie um MP4 ou MOV."
        ) from None
    arredondado = round(segundos, 1)
    if not MIN_VIDEO_SECONDS <= arredondado <= MAX_VIDEO_SECONDS:
        recebido = f"{arredondado:.1f}".replace(".", ",")
        raise ValidationError(
            f"{nome} tem {recebido}s. O vídeo da peça deve ter de "
            f"{MIN_VIDEO_SECONDS:.0f} a {MAX_VIDEO_SECONDS:.0f} segundos.",
        )


def validar_quantidade(quantidade: int) -> None:
    if quantidade == 0:
        raise ValidationError("Envie ao menos um arquivo.")
    if quantidade > MAX_FILES_PER_REQUEST:
        raise ValidationError(
            f"No máximo {MAX_FILES_PER_REQUEST} arquivos por envio.",
        )
