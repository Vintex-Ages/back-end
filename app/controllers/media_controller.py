"""Upload e leitura de mídia (VE-04, back-end#73).

Fecha a única ponta que faltava para o cadastro de peça com IA funcionar de
ponta a ponta: as fotos do vendedor passam a ter um endereço que o servidor
alcança, que é o que `POST /api/ai/listing-suggestions` precisa receber (ele
baixa cada URL antes de mandar ao modelo multimodal).

Divisão de responsabilidade, seguindo o que o `MediaStorage` já declarava:
objeto é dele (VE-16), formato e tamanho são do `media_rules`, e a URL é daqui.
"""

from __future__ import annotations

import logging

from app.core.errors import NotFound
from app.schemas.media_schema import MediaItemResponse, MediaUploadResponse
from app.services import media_rules
from app.services.media_storage import MEDIA_PREFIXES, MediaKind, MediaStorage

logger = logging.getLogger(__name__)


class ArquivoRecebido:
    """O que o controller precisa de um upload, sem depender do `UploadFile`.

    Existe para o controller ser testável sem montar multipart: a rota lê o
    arquivo e entrega nome, tipo e bytes.
    """

    def __init__(self, nome: str, content_type: str | None, conteudo: bytes) -> None:
        self.nome = nome
        self.content_type = content_type
        self.conteudo = conteudo


class MediaController:
    def __init__(self, storage: MediaStorage, base_url: str) -> None:
        self.storage = storage
        # Sem barra no fim para a concatenação não gerar `//`.
        self.base_url = base_url.rstrip("/")

    def upload(
        self, kind: MediaKind, arquivos: list[ArquivoRecebido]
    ) -> MediaUploadResponse:
        media_rules.validar_quantidade(len(arquivos))

        total = 0
        # Valida tudo antes de subir qualquer coisa: subir metade e falhar na
        # outra deixaria objeto órfão no bucket, sem nada apontando para ele.
        for arquivo in arquivos:
            content_type = media_rules.validar_tipo(kind, arquivo.content_type)
            total += len(arquivo.conteudo)
            media_rules.validar_tamanho(arquivo.nome, len(arquivo.conteudo), total)
            arquivo.content_type = content_type

        itens: list[MediaItemResponse] = []
        for arquivo in arquivos:
            assert arquivo.content_type is not None  # garantido pelo laço acima
            key = self.storage.upload(kind, arquivo.conteudo, arquivo.content_type)
            itens.append(
                MediaItemResponse(
                    key=key,
                    # Só tipo público ganha URL. Comprovante recebia uma URL
                    # absoluta que a própria rota de leitura recusa: 201 no
                    # upload e 404 na leitura (back-end#220). A API não entrega
                    # endereço que ela mesma nega.
                    url=(
                        self.url_publica(key)
                        if kind in media_rules.PUBLIC_KINDS
                        else None
                    ),
                    content_type=arquivo.content_type,
                    size=len(arquivo.conteudo),
                )
            )

        return MediaUploadResponse(kind=kind, items=itens)

    def url_publica(self, key: str) -> str:
        return f"{self.base_url}/api/media/{key}"

    def read_publico(self, key: str) -> tuple[bytes, str]:
        """Bytes de uma mídia pública.

        Chave fora dos prefixos públicos responde igual a chave inexistente: um
        comprovante de pagamento não deve ser legível por quem descobriu o
        endereço, e a resposta não deve nem confirmar que ele existe.
        """
        if not self._e_publica(key):
            raise NotFound("Mídia não encontrada.")

        try:
            return self.storage.read_with_type(key)
        except Exception:  # noqa: BLE001 - erro do S3 vira 404 de domínio
            logger.info("Mídia não encontrada no storage: %s", key)
            raise NotFound("Mídia não encontrada.") from None

    @staticmethod
    def _e_publica(key: str) -> bool:
        # Chave de S3 é string opaca, então `products/photos/../../x` hoje é só
        # outra chave que não existe, e não um caminho para fora do prefixo. A
        # recusa está aqui para a garantia ser desta regra e não da semântica do
        # provedor: se o storage um dia for sistema de arquivos, o prefixo
        # sozinho deixaria de proteger.
        if ".." in key or key.startswith("/"):
            return False

        return any(
            key.startswith(MEDIA_PREFIXES[kind]) for kind in media_rules.PUBLIC_KINDS
        )
