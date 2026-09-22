from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=80)
    style: str | None = Field(default=None, max_length=80)
    brand: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=30)
    condition: str | None = Field(default=None, max_length=50)
    price: Decimal | None = Field(default=None, gt=0, decimal_places=2)


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
