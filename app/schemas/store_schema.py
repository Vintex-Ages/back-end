from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    logo_url: AnyHttpUrl
    document_type: Literal["CPF", "CNPJ"]
    document_value: str = Field(min_length=1, max_length=18)
    terms_version: str = Field(min_length=1, max_length=20)


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    name: str
    description: str | None
    logo_url: str | None
    document_type: str
    document_value: str
    terms_version: str | None
    terms_accepted_at: datetime | None
