from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


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

    # `Decimal` sai como string em JSON se ninguem interferir. O front absorvia
    # com `Number(...)`, mas a mesma peca chegava como numero pelo feed e como
    # string por aqui -- `#212`.
    @field_serializer("price")
    def serializar_preco(self, price: Decimal) -> float:
        return float(price)


class ProductManagementPage(BaseModel):
    items: list[ProductManagementResponse]
    page: int
    page_size: int
    total: int
