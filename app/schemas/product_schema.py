from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductFilters(BaseModel):
    category: str | None = None
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    size: str | None = None
    brand: str | None = None
    condition: str | None = None
    color: str | None = None

    @model_validator(mode="after")
    def validate_price_range(self) -> "ProductFilters":
        if (
            isinstance(self.price_min, Decimal)
            and isinstance(self.price_max, Decimal)
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min deve ser menor ou igual a price_max")
        return self

    def applied(self) -> dict[str, str | Decimal]:
        return {
            key: value for key, value in self.model_dump().items() if value is not None
        }


def product_filters(
    category: str | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    size: str | None = None,
    brand: str | None = None,
    condition: str | None = None,
    color: str | None = None,
) -> ProductFilters:
    return ProductFilters(
        category=category,
        price_min=price_min,
        price_max=price_max,
        size=size,
        brand=brand,
        condition=condition,
        color=color,
    )


class FeedStoreResponse(BaseModel):
    id: int
    name: str


class ProductFeedItemResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    store: FeedStoreResponse
    status: str


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ProductFeedItemResponse]
    page: int
    page_size: int
    total: int
    applied_filters: dict[str, str | Decimal] = Field(default_factory=dict)
