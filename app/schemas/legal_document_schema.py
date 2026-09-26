from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LegalDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_type: str
    version: str
    content: str
    published_at: datetime
