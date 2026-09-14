"""Schemas do recurso do próprio usuário (`/api/users/me/*`)."""

from app.schemas.auth_schema import UserIdentity


class MeResponse(UserIdentity):
    is_seller: bool
