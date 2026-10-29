"""Schemas da avaliação da loja (back-end#267).

Só a nota, sem comentário (RN-75). A faixa de 1 a 5 é conferida aqui, para a
resposta ser um 422 com o campo, e de novo no CHECK do banco.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class StoreRatingCreate(BaseModel):
    order_id: int
    score: int = Field(ge=1, le=5)


class StoreRatingResponse(BaseModel):
    id: int
    store_id: int
    order_id: int
    score: int
    created_at: datetime
