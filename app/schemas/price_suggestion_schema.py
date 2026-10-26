"""Contrato do `POST /api/ai/price-suggestions` (BE-US018-1, back-end#254).

O mesmo que o `suggestPrice` do front (`vintexAiService`) já manda e lê.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator


class PriceSuggestionRequest(BaseModel):
    """`name` é o único obrigatório; os outros refinam a semelhança.

    O formulário manda os campos que ainda não foram preenchidos como `""`:
    vazio vale o mesmo que ausente.
    """

    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    brand: str | None = Field(default=None, max_length=80)
    condition: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def _nome_sem_espacos(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator(
        "category", "brand", "condition", "size", "description", mode="before"
    )
    @classmethod
    def _vazio_e_ausente(cls, valor: object) -> object:
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


class PriceSuggestionResponse(BaseModel):
    """`min` e `max` nulos quando não há base suficiente: 200, não erro.

    `based_on` é quantas peças do catálogo sustentam a faixa, para o vendedor
    julgar a comparação em vez de confiar no número.
    """

    min: Decimal | None
    max: Decimal | None
    justification: str
    based_on: int

    # Sem isto, o `Decimal` sai como string no JSON (`#212`).
    @field_serializer("min", "max")
    def _como_numero(self, valor: Decimal | None) -> float | None:
        return float(valor) if valor is not None else None
