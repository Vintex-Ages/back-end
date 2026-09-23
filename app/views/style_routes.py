from fastapi import APIRouter, Depends

from app.controllers.style_controller import StyleController
from app.schemas.style_schema import StylesResponse

router = APIRouter(prefix="/styles", tags=["Styles"])


def get_controller() -> StyleController:
    return StyleController()


@router.get("", response_model=StylesResponse)
def list_styles(
    controller: StyleController = Depends(get_controller),
) -> StylesResponse:
    return controller.get_all()
