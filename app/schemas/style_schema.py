from pydantic import BaseModel


class StyleResponse(BaseModel):
    type: str
    value: str
    label: str
    description: str


class StylesResponse(BaseModel):
    styles: list[StyleResponse]
