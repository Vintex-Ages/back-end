from pydantic import BaseModel


class UserMeResponse(BaseModel):
    id: int
    name: str
    email: str
    is_seller: bool
