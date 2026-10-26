"""Contrato do `POST /api/ai/chat` (BE-US027-3, back-end#149).

Eventos SSE combinados com o front (`FE-SVC-vintex-ai-chat`, front-end#199):
`text | products | interpreted | done | error`. Esta entrega só produz
`products`, `done` e `error` — `text` (geração de texto conversacional) e
`interpreted` (separação filtro/similaridade) dependem de capacidade que
ainda não existe (`AIProvider` só implementa `embed` de verdade hoje) e
ficam para a Sprint 3, conforme a própria issue #149 declara. `ChatEvent`
já inclui os dois para o transporte não precisar mudar quando entrarem.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.product_schema import ProductFeedItemResponse
from app.services.ai.base import ChatTurn, InterpretedQuery, SearchDone, SearchTextDelta


class ChatRequest(BaseModel):
    messages: list[ChatTurn]


class ChatProductsEvent(BaseModel):
    type: Literal["products"] = "products"
    products: list[ProductFeedItemResponse]


class ChatErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class ChatQuotaEvent(BaseModel):
    """A cota do chat acabou (back-end#258).

    É um `error`, com `code` e `retry_at` (ISO 8601, UTC): os nomes que o
    `vintexAiService` do front já lê. Com `code: quota_exceeded`, a tela mostra
    o aviso de cota e trava o envio até `retry_at`.
    """

    type: Literal["error"] = "error"
    code: Literal["quota_exceeded"] = "quota_exceeded"
    message: str
    retry_at: str


ChatEvent = (
    SearchTextDelta
    | ChatProductsEvent
    | InterpretedQuery
    | SearchDone
    | ChatErrorEvent
    | ChatQuotaEvent
)
