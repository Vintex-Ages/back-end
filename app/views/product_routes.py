from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.errors import ValidationError
from app.core.pagination import PageParams, page_params
from app.database import get_db
from app.schemas.product_management_schema import (
    ProductManagementPage,
)
from app.schemas.product_schema import (
    FeedResponse,
    ProductAIStatusResponse,
    ProductDetailResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFilters,
    SalesSummaryResponse,
)
from app.services.product_embedding import gerar_embedding_da_peca

router = APIRouter(prefix="/products", tags=["Products"])

# Recurso do usuário logado (ADR 0001 §4): peças do próprio vendedor.
me_router = APIRouter(prefix="/users/me/products", tags=["Products"])

# Vendas do próprio vendedor. Router separado porque o caminho é outro
# (`/users/me/sales`), e no mesmo arquivo porque o dado é peça — o
# `ProductController` e o `get_controller` daqui são os mesmos.
sales_router = APIRouter(prefix="/users/me/sales", tags=["Sales"])


def get_controller(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> ProductController:
    # O vetor da busca por semelhança é gerado depois da resposta (back-end#245).
    return ProductController(
        db,
        agendar_embedding=lambda product_id: background_tasks.add_task(
            gerar_embedding_da_peca, product_id
        ),
    )


def product_filters(
    category: str | None = Query(None),
    price_min: Decimal | None = Query(None),
    price_max: Decimal | None = Query(None),
    size: str | None = Query(None),
    brand: str | None = Query(None),
    condition: str | None = Query(None),
    color: str | None = Query(None),
    store_id: int | None = Query(None, gt=0),
    city: str | None = Query(None),
    state: str | None = Query(None),
) -> ProductFilters:
    try:
        return ProductFilters(
            category=category,
            price_min=price_min,
            price_max=price_max,
            size=size,
            brand=brand,
            condition=condition,
            color=color,
            store_id=store_id,
            city=city,
            state=state,
        )
    except PydanticValidationError as exc:
        fields = {
            ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
            for error in exc.errors()
        }
        raise ValidationError("Dados inválidos na requisição.", fields=fields) from exc


@router.get("", response_model=FeedResponse)
def list_products(
    params: PageParams = Depends(page_params),
    q: str | None = Query(
        None, max_length=200, description="Termo de busca; ignora acento e caixa."
    ),
    filters: ProductFilters = Depends(product_filters),
    sort: Literal["recent"] = Query(
        "recent", description="Ordenação do feed; atualmente apenas recentes."
    ),
    controller: ProductController = Depends(get_controller),
) -> FeedResponse:
    return controller.get_feed(params, filters, q=q)


@me_router.get("", response_model=ProductManagementPage)
def list_seller_products(
    status: Literal["rascunho", "ativo", "vendido", "despublicado"] | None = Query(
        None, description="Situação da peça; sem filtro, o rascunho fica de fora."
    ),
    params: PageParams = Depends(page_params),
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductManagementPage:
    # `rascunho` entrou no filtro no #271: a aba de rascunhos do painel pede
    # `?status=rascunho`. Sem filtro a lista continua sem rascunho (RN-51),
    # então esta rota não é o caminho para "todas as situações".
    return controller.list_for_seller(user_id, params, status)


# Antes de `/products/{id}`: a tela de edição precisa da peça em qualquer
# situação, e o detalhe público responde 404 para despublicada e não traz
# rascunho. Mesmo schema das transições, que é o que o mapeador do front lê.
@me_router.get("/{product_id}", response_model=ProductDraftResponse)
def get_seller_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.get_owned_detail(user_id, product_id)


@sales_router.get("/summary", response_model=SalesSummaryResponse)
def get_sales_summary(
    period: Literal["month", "30d", "all"] = Query("month"),
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> SalesSummaryResponse:
    return controller.sales_summary(user_id, period)


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    summary="Detalhe da peça",
    responses={404: {"description": "PRODUCT_NOT_FOUND"}},
)
def get_product_detail(
    product_id: int,
    controller: ProductController = Depends(get_controller),
) -> ProductDetailResponse:
    return controller.get_detail(product_id)


@me_router.patch("/{product_id}", response_model=ProductDraftResponse)
def update_product(
    product_id: int,
    data: ProductDraftUpdate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.update(user_id, product_id, data)


# Descartar o rascunho é apagar a peça (#271): ela nunca foi pública e não há
# histórico a preservar. As fotos vão junto, pelo cascade do modelo. Peça de
# outro vendedor responde 404, igual a inexistente.
@me_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Descarta um rascunho",
    responses={
        404: {"description": "PRODUCT_NOT_FOUND"},
        409: {"description": "PRODUCT_NOT_EDITABLE | PRODUCT_SOLD"},
    },
)
def discard_draft(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> None:
    controller.discard_draft(user_id, product_id)


# Mesmo schema das outras transicoes do recurso (`#230`): o front trata as tres
# num mapeador so, que le `store`, `images` e `ai_corrections`. O schema reduzido
# que ficava aqui derrubava a tela do vendedor assim que o mock fosse desligado.
@me_router.post("/{product_id}/unpublish", response_model=ProductDraftResponse)
def unpublish_product(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.unpublish(user_id, product_id)


@me_router.post(
    "", response_model=ProductDraftResponse, status_code=status.HTTP_201_CREATED
)
def create_draft(
    data: ProductDraftCreate,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.create_draft(user_id, data)


@me_router.post("/{product_id}/publish", response_model=ProductDraftResponse)
def publish_draft(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductDraftResponse:
    return controller.publish(user_id, product_id)


@me_router.get("/{product_id}/ai-status", response_model=ProductAIStatusResponse)
def get_product_ai_status(
    product_id: int,
    user_id: int = Depends(get_current_user_id),
    controller: ProductController = Depends(get_controller),
) -> ProductAIStatusResponse:
    return controller.get_ai_status(product_id, user_id)
