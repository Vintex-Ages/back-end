"""Recurso do próprio usuário logado.

Ver `.ai/adr/0001-fundacao-http-kit-api.md` §4: `/api/users/me/*` é o
prefixo de todo recurso do usuário logado (ações de credencial ficam em
`/api/auth/*`). Implementa as issues #84 (`/me`) e #80 (`/me/preferences`).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.user_controller import UserController
from app.core.security import require_auth
from app.database import get_db
from app.models.user import User
from app.schemas.user_schema import MeResponse, PreferencesRequest, PreferencesResponse

router = APIRouter(prefix="/users", tags=["Users"])


def get_controller(db: Session = Depends(get_db)) -> UserController:
    return UserController(db)


@router.get("/me", response_model=MeResponse)
def get_me(
    user: User = Depends(require_auth),
    controller: UserController = Depends(get_controller),
) -> MeResponse:
    return controller.get_me(user)


@router.get("/me/preferences", response_model=PreferencesResponse)
def get_my_preferences(
    user: User = Depends(require_auth),
    controller: UserController = Depends(get_controller),
) -> PreferencesResponse:
    """Preferências do usuário logado, na ordem em que foram gravadas."""
    return controller.get_preferences(user)


@router.put("/me/preferences", response_model=PreferencesResponse)
def replace_my_preferences(
    payload: PreferencesRequest,
    user: User = Depends(require_auth),
    controller: UserController = Depends(get_controller),
) -> PreferencesResponse:
    """Substitui o conjunto inteiro de preferências. Idempotente; lista vazia
    limpa o perfil. Itens repetidos no corpo são gravados uma vez só."""
    return controller.replace_preferences(user, payload)
