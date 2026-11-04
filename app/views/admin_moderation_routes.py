"""Moderação de anúncios da administradora (back-end#327).

Router próprio sob o prefixo `/admin`, e não mais rotas no `admin_routes.py`:
moderação e fila de comprovantes são domínios diferentes, e separar deixa cada
arquivo com uma responsabilidade. A guarda de papel é a mesma do outro router,
declarada aqui — esquecer o `Depends` numa rota nova não abre a rota (RN-32), e
`tests/test_admin_guard.py` confere no OpenAPI que toda rota de `/api/admin`
responde 401/403 sem o papel.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.admin_moderation_controller import AdminModerationController
from app.core.errors import ValidationError
from app.core.pagination import Page, PageParams, page_params
from app.core.security import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.admin_moderation_schema import (
    ModeratedProductResponse,
    ModerationResponse,
    UnpublishRequest,
)
from app.services.product_embedding import gerar_embedding_da_peca

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def get_moderation_controller(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> AdminModerationController:
    # O vetor é gerado depois da resposta, como na publicação do vendedor: a
    # peça devolvida à vitrine volta a valer na busca por semelhança.
    return AdminModerationController(
        db,
        agendar_embedding=lambda product_id: background_tasks.add_task(
            gerar_embedding_da_peca, product_id
        ),
    )


@router.post(
    "/products/{product_id}/unpublish",
    response_model=ModerationResponse,
    summary="Tira o anúncio do ar com motivo, data e autor",
    responses={
        403: {"description": "ADMIN_REQUIRED: inclusive o dono da peça"},
        404: {"description": "PRODUCT_NOT_FOUND"},
        409: {
            "description": "PRODUCT_SOLD · PRODUCT_NOT_EDITABLE: peça em pedido aberto"
        },
        422: {"description": "motivo vazio"},
    },
)
def suspend_product(
    product_id: int,
    data: UnpublishRequest,
    admin: User = Depends(require_admin),
    controller: AdminModerationController = Depends(get_moderation_controller),
) -> ModerationResponse:
    return controller.suspend(product_id, data.reason, admin)


@router.post(
    "/products/{product_id}/publish",
    response_model=ModerationResponse,
    summary="Devolve à vitrine a peça Suspensa pela moderação",
    responses={
        403: {"description": "ADMIN_REQUIRED"},
        404: {"description": "PRODUCT_NOT_FOUND"},
        409: {"description": "PRODUCT_NOT_SUSPENDED"},
        422: {"description": "peça sem foto"},
    },
)
def restore_product(
    product_id: int,
    admin: User = Depends(require_admin),
    controller: AdminModerationController = Depends(get_moderation_controller),
) -> ModerationResponse:
    return controller.restore(product_id, admin)


@router.get(
    "/products",
    response_model=Page[ModeratedProductResponse],
    summary="Peças Suspensas pela moderação, mais recente primeiro",
    responses={
        403: {"description": "ADMIN_REQUIRED"},
        422: {"description": "moderated diferente de true"},
    },
)
def list_moderated_products(
    moderated: bool = Query(
        False,
        description="Só a lista de Suspensas; qualquer outro valor responde 422.",
    ),
    params: PageParams = Depends(page_params),
    controller: AdminModerationController = Depends(get_moderation_controller),
) -> Page[ModeratedProductResponse]:
    if not moderated:
        raise ValidationError(
            "Esta listagem é só das peças suspensas pela moderação.",
            fields={"moderated": "Use moderated=true."},
        )
    return controller.list_suspended(params)
