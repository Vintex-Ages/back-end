"""Rotas de mídia (VE-04, back-end#73).

Duas rotas, com públicos diferentes de propósito:

- `POST /api/users/me/media` exige login (ADR 0001 §4: recurso do usuário
  logado vive sob `/users/me/*`). É ação de vendedor.
- `GET /api/media/{key}` é pública, porque foto de peça anunciada é pública, e
  é por essa URL que o servidor baixa a foto ao gerar a sugestão do anúncio.
  Só serve os prefixos públicos; ver `MediaController.read_publico`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import Response

from app.config import settings
from app.controllers.media_controller import ArquivoRecebido, MediaController
from app.core.security import require_auth
from app.models.user import User
from app.schemas.media_schema import MediaUploadResponse
from app.services.media_storage import MediaKind, MediaStorage

me_router = APIRouter(prefix="/users/me/media", tags=["Media"])
public_router = APIRouter(prefix="/media", tags=["Media"])


def get_controller(request: Request) -> MediaController:
    """A base da URL vem da configuração e, na falta dela, da requisição.

    Em desenvolvimento a base da requisição já é a certa (`localhost:8000`),
    que o próprio servidor alcança. Em outro ambiente, onde o endereço que o
    navegador usa não é o que o servidor usa, `PUBLIC_BASE_URL` resolve.
    """
    base = settings.PUBLIC_BASE_URL or str(request.base_url)
    return MediaController(MediaStorage.from_settings(), base)


@me_router.post(
    "", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_media(
    files: list[UploadFile] = File(...),
    kind: MediaKind = Form(default="photo"),
    user: User = Depends(require_auth),
    controller: MediaController = Depends(get_controller),
) -> MediaUploadResponse:
    recebidos = [
        ArquivoRecebido(
            nome=arquivo.filename or "arquivo",
            content_type=arquivo.content_type,
            conteudo=await arquivo.read(),
        )
        for arquivo in files
    ]
    return controller.upload(kind, recebidos)


@public_router.get("/{key:path}")
def get_media(
    key: str,
    controller: MediaController = Depends(get_controller),
) -> Response:
    conteudo, content_type = controller.read_publico(key)
    # `immutable`: a chave é um uuid novo a cada upload, então o conteúdo de uma
    # chave nunca muda.
    return Response(
        content=conteudo,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
