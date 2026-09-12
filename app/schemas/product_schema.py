from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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


class ProductMediaResponse(BaseModel):
    type: str = "image"
    url: str
    position: int


class ProductDetailStoreResponse(BaseModel):
    id: int
    name: str
    logo_url: str | None


class ProductDetailResponse(BaseModel):
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
    status: str
    city: str | None
    state: str | None
    media: list[ProductMediaResponse]
    store: ProductDetailStoreResponse
