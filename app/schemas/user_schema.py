"""Schemas do recurso do próprio usuário (`/api/users/me/*`)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.auth_schema import UserIdentity

# Limites espelham as colunas de `user_preferences` (String(50) e String(100)).
# `strip_whitespace` vem antes do `min_length`: "  " não passa como valor.
PreferenceType = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
PreferenceValue = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

# Teto de itens por PUT: o onboarding manda poucas escolhas; o limite só
# impede que um corpo gigante vire milhares de INSERTs.
MAX_PREFERENCES = 50


class MeResponse(UserIdentity):
    is_seller: bool


class PreferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: PreferenceType
    value: PreferenceValue


class PreferencesRequest(BaseModel):
    preferences: list[PreferenceItem] = Field(max_length=MAX_PREFERENCES)


class PreferencesResponse(BaseModel):
    preferences: list[PreferenceItem]
