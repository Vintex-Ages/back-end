from datetime import timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.comissao import dividir
from app.core.errors import AppError, Conflict, ErrorCode, NotFound, ValidationError
from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_ai_correction import ProductAiCorrection
from app.models.product_image import ProductImage
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.product_management_schema import ProductManagementPage
from app.schemas.product_schema import (
    AiCorrectionResponse,
    FeedResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFeedItemResponse,
    ProductFilters,
    ProductMediaResponse,
    ProductStoreResponse,
    SalesSummaryResponse,
    SuggestionsResponse,
)
from app.services.ai.base import ImageAnalysisResult


class ProductController:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def get_feed(
        self, params: PageParams, filters: ProductFilters, q: str | None = None
    ) -> FeedResponse:
        rows, total = self.repository.get_active_feed(params, filters, q=q)

        if q and not rows:
            return self._sem_resultado(params, filters, q)

        return FeedResponse(
            items=[ProductFeedItemResponse.from_row(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total=total,
            applied_filters=filters.applied(),
        )

    def _sem_resultado(
        self, params: PageParams, filters: ProductFilters, q: str
    ) -> FeedResponse:
        """Busca sem correspondencia: devolve pecas parecidas e explica o motivo.

        Tenta cada palavra do termo isoladamente ("jaqueta jeans" vira
        "jaqueta" e depois "jeans"). Se nenhuma achar, cai para o catalogo
        com os mesmos filtros, de modo que a busca nunca volta vazia enquanto
        houver peca. Catalogo vazio devolve vazio, sem erro.
        """
        for palavra in self._palavras(q):
            rows, _ = self.repository.get_active_feed(params, filters, q=palavra)
            if rows:
                return self._alternativas(params, filters, q, rows)

        rows, _ = self.repository.get_active_feed(params, filters)
        if not rows:
            return FeedResponse(
                items=[],
                page=params.page,
                page_size=params.page_size,
                total=0,
                applied_filters=filters.applied(),
            )
        return self._alternativas(params, filters, q, rows)

    def _alternativas(
        self,
        params: PageParams,
        filters: ProductFilters,
        q: str,
        rows: list[ProductFeedRow],
    ) -> FeedResponse:
        return FeedResponse(
            items=[],
            page=params.page,
            page_size=params.page_size,
            # `total` conta o que esta sendo mostrado. No fallback a lista
            # exibida e `suggestions.items`, e o front faz `setTotal(total)`
            # sem olhar o `match_type` — com zero aqui, a tela diz "0 pecas
            # encontradas" em cima de uma grade cheia.
            total=len(rows),
            applied_filters=filters.applied(),
            match_type="fallback",
            suggestions=SuggestionsResponse(
                reason=f'Nenhum resultado para "{q}". Veja outras peças disponíveis.',
                items=[ProductFeedItemResponse.from_row(row) for row in rows],
            ),
        )

    @staticmethod
    def _palavras(q: str) -> list[str]:
        """Palavras do termo com 3+ letras, exceto quando repete a consulta.

        Quando so sobra uma palavra com 3+ letras e ela e o termo inteiro
        (busca de uma palavra so), nao adianta repetir a consulta que ja
        falhou. Mas um termo com duas ou mais palavras onde so uma tem 3+
        letras (ex.: "jaqueta a") ainda vale tentar isoladamente, pois e
        uma consulta diferente da original.
        """
        palavras = [p for p in q.split() if len(p) >= 3]
        if len(palavras) == 1 and palavras[0].lower() == q.strip().lower():
            return []
        return palavras

    def get_detail(self, product_id: int) -> ProductDetailResponse:
        product = self.repository.get_detail_by_id(product_id)

        if product is None or product.status == "despublicado":
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        address = product.store.address

        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            description=product.description or "",
            category=product.category or "",
            style=product.style or "",
            brand=product.brand or "",
            color=product.color or "",
            size=product.size or "",
            condition=product.condition or "",
            price=product.price,
            status=product.status,
            city=address.city if address else "",
            state=address.state if address else "",
            media=[
                ProductMediaResponse(url=image.image_url, position=image.position)
                for image in product.images
            ],
            store=ProductDetailStoreResponse(
                id=product.store.id,
                name=product.store.name,
                logo_url=product.store.logo_url,
                verified=product.store.seller.verified,
            ),
        )

    def create_draft(
        self, user_id: int, data: ProductDraftCreate
    ) -> ProductDraftResponse:
        store = self.repository.get_store_for_user(user_id)
        if store is None:
            raise NotFound(
                "Você ainda não tem uma loja cadastrada.",
                code=ErrorCode.STORE_NOT_FOUND,
            )

        product = Product(
            store=store,
            name=data.name,
            description=data.description,
            category=data.category,
            style=data.style,
            brand=data.brand,
            color=data.color,
            size=data.size,
            condition=data.condition,
            price=data.price,
            status="rascunho",
            images=[
                ProductImage(image_url=url, position=position)
                for position, url in enumerate(data.images)
            ],
            ai_corrections=[
                ProductAiCorrection(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
                for correction in data.ai_corrections
            ],
        )
        self.repository.create(product)
        self.repository.commit()
        return self._to_response(product)

    def update(
        self, user_id: int, product_id: int, data: ProductDraftUpdate
    ) -> ProductDraftResponse:
        """Edita rascunho ou peça publicada/despublicada; vendida é imutável."""
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode ser editada.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status != "rascunho" and data.images == []:
            # Publicar exige foto (`publish`); editar não pode desfazer isso.
            raise ValidationError(
                "Peça publicada precisa de ao menos uma foto.",
                fields={"images": "Mantenha ao menos uma foto."},
            )

        updates = data.model_dump(
            exclude_unset=True, exclude={"images", "ai_corrections"}
        )
        for field, value in updates.items():
            setattr(product, field, value)

        if data.images is not None:
            product.images = [
                ProductImage(image_url=url, position=position)
                for position, url in enumerate(data.images)
            ]

        for correction in data.ai_corrections:
            product.ai_corrections.append(
                ProductAiCorrection(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
            )

        self.repository.commit()
        return self._to_response(product)

    def publish(self, user_id: int, product_id: int) -> ProductDraftResponse:
        """Leva a peca para `ativo`, vindo de `rascunho` ou de `despublicado`.

        A `#145` declarou na secao Fronteira que publicar rascunho e republicar
        peca despublicada sao a mesma transicao. A rota nasceu no `#159`
        aceitando so `rascunho`, e o `#157` contornou criando `republish` em vez
        de completar aqui. O front sempre chamou `publish` para as duas, e
        recebia 409 na segunda -- `#230`.
        """
        product = self._get_owned_publicavel(user_id, product_id)

        if not product.images:
            raise ValidationError(
                "Publicar exige ao menos uma foto.",
                fields={"images": "Adicione ao menos uma foto antes de publicar."},
            )

        product.status = "ativo"
        self.repository.commit()
        return self._to_response(product)

    def _get_owned_publicavel(self, user_id: int, product_id: int) -> Product:
        """Peca do vendedor que pode ir para `ativo`: rascunho ou despublicada.

        Vendida responde com o codigo proprio e nao com o conflito generico
        (RN-53) -- quem chama precisa distinguir "ja esta no ar" de "nao mexe
        mais nesta".
        """
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode mudar de situação.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status == "ativo":
            raise Conflict("Esta peça já está publicada.")
        return product

    def _get_owned(self, user_id: int, product_id: int) -> Product:
        product = self.repository.get_by_id(product_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)
        if product.store.seller.user_id != user_id:
            # 404 e não 403, pela mesma regra que `get_for_seller` documenta:
            # peça de outro vendedor responde igual a peça inexistente. Um 403
            # confirma que aquele id existe, e rascunho alheio não é público.
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)
        return product

    def _to_response(self, product: Product) -> ProductDraftResponse:
        store = product.store
        return ProductDraftResponse(
            id=product.id,
            name=product.name,
            description=product.description,
            category=product.category,
            style=product.style,
            brand=product.brand,
            color=product.color,
            size=product.size,
            condition=product.condition,
            price=product.price,
            quantity=product.quantity,
            status=product.status,
            store=ProductStoreResponse(
                id=store.id,
                name=store.name,
                city=store.address.city if store.address else None,
            ),
            images=[image.image_url for image in product.images],
            ai_corrections=[
                AiCorrectionResponse(
                    field=correction.field,
                    suggested=correction.suggested,
                    final=correction.final,
                )
                for correction in product.ai_corrections
            ],
        )

    def get_ai_status(self, product_id: int, user_id: int) -> ProductAIStatusResponse:
        product = self.repository.get_for_seller(product_id, user_id)
        if product is None:
            raise NotFound("Peça não encontrada.", code=ErrorCode.PRODUCT_NOT_FOUND)

        status: ProductAIStatusValue = (
            "not_requested" if product.ai_status is None else product.ai_status
        )
        return ProductAIStatusResponse(
            status=status,
            error=product.ai_error,
            suggestions=(
                ImageAnalysisResult.model_validate(product.ai_suggestions)
                if product.ai_suggestions is not None
                else None
            ),
        )

    def list_for_seller(
        self, user_id: int, params: PageParams, status: str | None
    ) -> ProductManagementPage:
        page = self.repository.list_for_seller(user_id, params, status)
        return ProductManagementPage(
            items=page.items,
            page=page.page,
            page_size=page.page_size,
            total=page.total,
        )

    def get_owned_detail(self, user_id: int, product_id: int) -> ProductDraftResponse:
        """Peça do vendedor em qualquer situação (back-end#234).

        O detalhe público (`get_detail`) não serve para a tela de edição: ele
        responde 404 para peça despublicada e não devolve rascunho. Peça de
        outro vendedor responde 404 pela regra do `_get_owned`.
        """
        return self._to_response(self._get_owned(user_id, product_id))

    def sales_summary(
        self, user_id: int, period: Literal["month", "30d", "all"]
    ) -> SalesSummaryResponse:
        """Bruto, comissão de 9% e líquido do vendedor no período (#146).

        `month` é o mês corrente, do dia 1; `30d` são os últimos 30 dias;
        `all` não tem corte. Sem venda no período devolve zero, não erro.
        """
        agora = utcnow_naive()
        if period == "month":
            desde = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "30d":
            desde = agora - timedelta(days=30)
        else:
            desde = None
        quantidade, bruto = self.repository.sales_summary(user_id, desde)
        comissao, liquido = dividir(bruto)
        return SalesSummaryResponse(
            period=period,
            sold_count=quantidade,
            gross=bruto,
            commission=comissao,
            net=liquido,
        )

    def unpublish(self, user_id: int, product_id: int) -> ProductDraftResponse:
        """`ativo -> despublicado`: sai da vitrine, historico preservado (RN-52).

        So tira do ar. O caminho de volta e o `publish`, que exige foto.

        Antes isto era um `set_status` que alternava nos dois sentidos, e a rota
        `republish` usava o sentido `-> ativo` sem checar foto: peca despublicada
        sem imagem voltava com 200 e entrava no feed publico. O comentario que
        estava aqui afirmava justamente que esse caminho nao existia. A rota saiu
        na `#230`, e com um sentido so essa contradicao nao volta.
        """
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode mudar de situação.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status != "ativo":
            raise AppError(
                "Só peça com situação 'ativo' pode ir para 'despublicado'.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
                status_code=409,
            )
        product.status = "despublicado"
        self.repository.commit()
        return self._to_response(product)
