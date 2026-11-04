from decimal import Decimal
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.controllers.media_controller import ArquivoRecebido
from app.controllers.product_controller import ProductController
from app.core.current_user import get_current_user_id
from app.core.errors import ValidationError
from app.core.pagination import DEFAULT_PAGE_SIZE, PageParams, page_params
from app.core.security import optional_user
from app.database import get_db
from app.models.user import User
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
    ProductImageSearchResponse,
    SalesSummaryResponse,
)
from app.services import media_rules
from app.services.chat_quota import chave_da_pessoa
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


def _filtros_do_catalogo(
    *,
    category: str | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
    size: str | None,
    brand: str | None,
    condition: str | None,
    color: str | None,
    city: str | None,
    state: str | None,
    store_id: int | None = None,
) -> ProductFilters:
    """Monta e valida os filtros do catálogo, venham de query ou formulário."""
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
    return _filtros_do_catalogo(
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


def image_search_filters(
    category: str | None = Form(None),
    price_min: Decimal | None = Form(None, ge=0),
    price_max: Decimal | None = Form(None, ge=0),
    size: str | None = Form(None),
    brand: str | None = Form(None),
    condition: str | None = Form(None),
    color: str | None = Form(None),
    city: str | None = Form(None),
    state: str | None = Form(None),
) -> ProductFilters:
    """Os filtros do catálogo como campos do multipart (back-end#255).

    Mesmos nomes e validação do feed (RN-40), sem `store_id`: o contrato da
    busca por foto lista os filtros do catálogo e não a loja.
    """
    return _filtros_do_catalogo(
        category=category,
        price_min=price_min,
        price_max=price_max,
        size=size,
        brand=brand,
        condition=condition,
        color=color,
        city=city,
        state=state,
    )


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


@router.post(
    "/search-by-image",
    response_model=ProductImageSearchResponse,
    summary="Busca peças parecidas com uma foto",
    responses={
        413: {"description": "IMAGE_TOO_LARGE: foto acima de 8 MiB"},
        415: {"description": "IMAGE_INVALID_TYPE: nem JPEG, PNG, WebP ou HEIC"},
        429: {"description": "QUOTA_EXCEEDED: cota diária da IA esgotada"},
        503: {"description": "AI_UNAVAILABLE: análise da foto indisponível"},
    },
)
async def search_by_image(
    request: Request,
    image: UploadFile = File(
        ..., description="Foto da peça: JPEG, PNG, WebP ou HEIC, até 8 MiB."
    ),
    filters: ProductFilters = Depends(image_search_filters),
    page: int = Form(1, ge=1, description="Página, começando em 1."),
    # Público (RN-26), como o catálogo: sem sessão a cota conta pela origem
    # da requisição, como no chat (back-end#258).
    user: User | None = Depends(optional_user),
    controller: ProductController = Depends(get_controller),
) -> ProductImageSearchResponse:
    """Análise da foto -> texto -> vetor -> peças parecidas (BE-US031-1).

    A foto **não é gravada**: ela é lida para a análise e descartada. A
    resposta é o feed paginado, com a distância de cada peça e o que a IA
    leu da imagem (`interpreted`).
    """
    # Um byte além do teto basta para responder 413 sem carregar um arquivo
    # de qualquer tamanho na memória. Mesmo caminho do comprovante (#249).
    conteudo = await image.read(media_rules.MAX_BYTES_PER_FILE + 1)
    arquivo = ArquivoRecebido(
        nome=image.filename or "foto",
        content_type=image.content_type,
        conteudo=conteudo,
    )
    pessoa = chave_da_pessoa(
        user.id if user else None, request.client.host if request.client else None
    )
    # A rota é `async` só pelo `await image.read`; banco e provedor são
    # síncronos e, chamados direto, segurariam o event loop inteiro.
    return await run_in_threadpool(
        controller.search_by_image,
        arquivo,
        filters,
        PageParams(page=page, page_size=DEFAULT_PAGE_SIZE),
        pessoa,
    )


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
