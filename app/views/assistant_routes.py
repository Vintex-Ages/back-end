from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.controllers.assistant_controller import AssistantController
from app.core.security import require_auth
from app.database import get_db
from app.models.user import User
from app.schemas.chat_schema import ChatRequest
from app.schemas.product_schema import ListingSuggestionsRequest
from app.services.ai.base import ImageAnalysisResult

router = APIRouter(prefix="/ai", tags=["Assistant"])


def get_controller(db: Session = Depends(get_db)) -> AssistantController:
    return AssistantController(db)


@router.post("/listing-suggestions", response_model=ImageAnalysisResult)
def listing_suggestions(
    body: ListingSuggestionsRequest,
    # Acao de vendedor, e o servidor busca URLs que o chamador manda. A rota
    # irma (`ai-status`) foi para `/users/me/*` pelo mesmo motivo.
    user: User = Depends(require_auth),
    controller: AssistantController = Depends(get_controller),
) -> ImageAnalysisResult:
    return controller.suggest_listing(body.image_urls)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    controller: AssistantController = Depends(get_controller),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in controller.chat(body.messages):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
