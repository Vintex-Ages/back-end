"""Pedidos do comprador (back-end#247 e back-end#248).

Recurso do usuário logado — ADR 0001 §4, por isso `/users/me/orders`. Exige
login (RN-27), não exige ser vendedor.
"""

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.controllers.media_controller import ArquivoRecebido
from app.controllers.order_controller import OrderController
from app.core.current_user import get_current_user_id
from app.core.pagination import Page, PageParams, page_params
from app.database import get_db
from app.schemas.order_schema import (
    OrderCreate,
    OrderListItemResponse,
    OrderReceiptResponse,
    OrderResponse,
)
from app.services import media_rules
from app.services.media_storage import MediaStorage
from app.views.media_routes import get_media_storage

router = APIRouter(prefix="/users/me/orders", tags=["Orders"])


def get_controller(db: Session = Depends(get_db)) -> OrderController:
    return OrderController(db)


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria o pedido e reserva as peças",
    responses={
        409: {"description": "MIXED_STORES · PIECE_UNAVAILABLE · STORE_WITHOUT_PIX"},
    },
)
def create_order(
    data: OrderCreate,
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> OrderResponse:
    return controller.create(user_id, data)


@router.get(
    "",
    response_model=Page[OrderListItemResponse],
    summary="Lista os pedidos de quem está logado, mais recente primeiro",
)
def list_my_orders(
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> Page[OrderListItemResponse]:
    return controller.list_mine(user_id, params)


@router.post(
    "/{order_id}/receipt",
    response_model=OrderReceiptResponse,
    # O contrato traz `payment` com status, nome e data, sem `rejection_reason`.
    response_model_exclude_none=True,
    summary="Envia o comprovante do Pix e põe o pedido em análise",
    responses={
        404: {"description": "ORDER_NOT_FOUND: inexistente ou de outra pessoa"},
        409: {"description": "ORDER_NOT_AWAITING_RECEIPT"},
        413: {"description": "RECEIPT_TOO_LARGE: acima de 8 MiB"},
        415: {"description": "RECEIPT_INVALID_TYPE: nem imagem nem PDF"},
    },
)
async def submit_receipt(
    order_id: int,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
    storage: MediaStorage = Depends(get_media_storage),
) -> OrderReceiptResponse:
    # Lê no máximo um byte além do teto: basta para saber que passou e
    # responder 413, sem trazer para a memória um arquivo de qualquer tamanho.
    conteudo = await file.read(media_rules.MAX_BYTES_PER_FILE + 1)
    arquivo = ArquivoRecebido(
        nome=file.filename or "comprovante",
        content_type=file.content_type,
        conteudo=conteudo,
    )
    # A rota é `async` só para o `await file.read`. O resto (Postgres e upload
    # no S3) é síncrono: chamado direto, seguraria o event loop e pararia
    # todas as outras requisições do servidor enquanto o comprovante sobe. No
    # threadpool ele roda como uma rota `def` comum.
    return await run_in_threadpool(
        controller.submit_receipt, user_id, order_id, arquivo, storage
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Detalhe do pedido, com a chave Pix e a linha do tempo",
    responses={404: {"description": "ORDER_NOT_FOUND: inexistente ou de outra pessoa"}},
)
def get_my_order(
    order_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: OrderController = Depends(get_controller),
) -> OrderResponse:
    return controller.get_mine(user_id, order_id)
