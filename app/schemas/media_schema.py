"""Contrato do upload de mídia (VE-04, back-end#73)."""

from __future__ import annotations

from pydantic import BaseModel

from app.services.media_storage import MediaKind


class MediaItemResponse(BaseModel):
    """Um arquivo guardado.

    `url` é absoluta de propósito: quem consome manda essa URL para
    `POST /api/ai/listing-suggestions`, e é o servidor que baixa a foto para
    mandar ao modelo. URL relativa não serve para ele.
    """

    key: str
    # `None` para tipo nao publico (comprovante): a rota de leitura
    # recusa esses prefixos, entao devolver endereco seria mentir.
    url: str | None
    content_type: str
    size: int


class MediaUploadResponse(BaseModel):
    kind: MediaKind
    items: list[MediaItemResponse]
