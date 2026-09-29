from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProductManagementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    category: str | None
    style: str | None
    brand: str | None
    color: str | None
    size: str | None
    condition: str | None
    price: Decimal
    quantity: int
    status: str


class ProductManagementPage(BaseModel):
    items: list[ProductManagementResponse]
    page: int
    page_size: int
    total: int
