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
