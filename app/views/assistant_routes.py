from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.controllers.assistant_controller import AssistantController
from app.database import get_db
from app.schemas.chat_schema import ChatRequest

router = APIRouter(prefix="/ai", tags=["Assistant"])


def get_controller(db: Session = Depends(get_db)) -> AssistantController:
    return AssistantController(db)


@router.post("/chat")
async def chat(
    body: ChatRequest,
    controller: AssistantController = Depends(get_controller),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in controller.chat(body.messages):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
