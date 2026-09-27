from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

_DOCUMENT_DIGIT_LENGTH = {"CPF": 11, "CNPJ": 14}


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    logo_url: AnyHttpUrl
    document_type: Literal["CPF", "CNPJ"]
    document_value: str = Field(min_length=1, max_length=18)
    terms_version: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_document_value_length(self) -> "StoreCreate":
        digits = "".join(c for c in self.document_value if c.isdigit())
        expected = _DOCUMENT_DIGIT_LENGTH[self.document_type]
        if len(digits) != expected:
            raise ValueError(
                f"{self.document_type} deve ter {expected} dígitos "
                f"(recebeu {len(digits)})."
            )
        return self


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
