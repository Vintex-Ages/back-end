"""Recomendações do usuário logado (back-end#253).

Recurso do próprio usuário (ADR 0001 §4), por isso `/users/me/recommendations`.
Exige login (RN-27).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers.recommendation_controller import RecommendationController
from app.core.current_user import get_current_user_id
from app.core.pagination import DEFAULT_PAGE_SIZE, PageParams
from app.database import get_db
from app.schemas.product_schema import RecommendationsResponse

router = APIRouter(prefix="/users/me/recommendations", tags=["Recommendations"])


def get_controller(db: Session = Depends(get_db)) -> RecommendationController:
    return RecommendationController(db)


@router.get(
    "",
    response_model=RecommendationsResponse,
    summary="Peças recomendadas pelo perfil de estilo (Garimpados para Você)",
)
def get_recommendations(
    # Só `page`, como no contrato: o front pede páginas de 20.
    page: int = Query(1, ge=1, description="Página, começando em 1."),
    user_id: int = Depends(get_current_user_id),
    controller: RecommendationController = Depends(get_controller),
) -> RecommendationsResponse:
    return controller.recommend(
        user_id, PageParams(page=page, page_size=DEFAULT_PAGE_SIZE)
    )
