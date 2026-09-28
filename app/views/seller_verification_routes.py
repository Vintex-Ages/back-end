"""BE-US007-1 (back-end#143): selo Confiável por validação simulada.

Arquivo temporário: a #141 (back-end#141) ainda vai criar `store_routes.py`
com as demais rotas de loja (`POST`/`GET /api/users/me/store`). Quando aquele
PR entrar, esta rota migra para lá; até então fica isolada para não colidir
com o arquivo que a #141 está criando.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers.seller_controller import SellerController
from app.core.current_user import get_current_user_id
from app.database import get_db
from app.schemas.seller_schema import SellerVerificationResponse

router = APIRouter(prefix="/users/me/store", tags=["Sellers"])


def get_controller(db: Session = Depends(get_db)) -> SellerController:
    return SellerController(db)


@router.post("/verification", response_model=SellerVerificationResponse)
def verify_store(
    user_id: int = Depends(get_current_user_id),
    controller: SellerController = Depends(get_controller),
) -> SellerVerificationResponse:
    return controller.verify_store(user_id)
