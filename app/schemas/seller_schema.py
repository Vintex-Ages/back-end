from pydantic import BaseModel


class SellerVerificationResponse(BaseModel):
    verified: bool
