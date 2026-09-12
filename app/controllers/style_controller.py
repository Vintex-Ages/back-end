from app.constants.styles import STYLES
from app.schemas.style_schema import StyleResponse, StylesResponse


class StyleController:
    def get_all(self) -> StylesResponse:
        return StylesResponse(
            styles=[StyleResponse.model_validate(style) for style in STYLES]
        )
