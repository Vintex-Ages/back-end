"""Schemas do recurso do próprio usuário (`/api/users/me/*`)."""

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: int
    name: str
    email: str
    is_admin: bool
    is_seller: bool
