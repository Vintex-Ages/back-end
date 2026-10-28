from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.controllers.media_controller import ArquivoRecebido
from app.core.clock import utcnow_naive
from app.core.comissao import dividir
from app.core.errors import (
    AppError,
    Conflict,
    ErrorCode,
    NotFound,
    ServiceUnavailable,
    ValidationError,
)
from app.core.pagination import PageParams
from app.models.product import Product
from app.models.product_ai_correction import ProductAiCorrection
from app.models.product_image import ProductImage
from app.repositories.product_repository import (
    ProductFeedRow,
    ProductRepository,
    ProductSimilarRow,
)
from app.repositories.store_repository import StoreRepository
from app.schemas.product_management_schema import ProductManagementPage
from app.schemas.product_schema import (
    AiCorrectionResponse,
    FeedResponse,
    InterpretedPhotoResponse,
    ProductAIStatusResponse,
    ProductAIStatusValue,
    ProductDetailResponse,
    ProductDetailStoreResponse,
    ProductDraftCreate,
    ProductDraftResponse,
    ProductDraftUpdate,
    ProductFeedItemResponse,
    ProductFilters,
    ProductImageSearchItem,
    ProductImageSearchResponse,
    ProductMediaResponse,
    ProductStoreResponse,
    SalesSummaryResponse,
    SuggestionsResponse,
)
from app.services import media_rules
from app.services.ai import AIProviderError, get_ai_provider, modelo_de_embedding
from app.services.ai.base import ImageAnalysisResult, ImagePhoto
from app.services.ai.queue import ImageAnalysisQueueError, enqueue_image_analysis
from app.services.chat_quota import ChatQuota, CotaEsgotada
from app.services.product_embedding import (
    apagar_embedding,
    pedir_embedding,
    precisa_de_embedding,
    texto_da_foto,
    texto_da_peca,
)

logger = logging.getLogger(__name__)

# Mensagem única da busca por foto quando a IA não responde (RN-57): o
# provedor não é culpa de quem mandou a foto, e o front precisa poder dizer
# isso em vez de "nenhuma peça parecida".
_BUSCA_INDISPONIVEL = (
    "A busca por foto está indisponível agora. Tente de novo em instantes."
)


class ProductController:
    def __init__(
        self, db: Session, agendar_embedding: Callable[[int], None] | None = None
    ):
        self.repository = ProductRepository(db)
        self.stores = StoreRepository(db)
        # Mesmo orçamento diário do provedor que o chat (back-end#258): a
        # busca por foto gasta duas chamadas (análise e embedding), então
        # sem cota uma pessoa zeraria o dia do projeto.
        self.quota = ChatQuota(db)
        # Quem gera o vetor em segundo plano (back-end#245): a rota liga ao
        # `BackgroundTasks`. Sem ele, a peça fica `pending` e o backfill a
        # encontra, porque continua sem vetor.
        self._agendar_embedding = agendar_embedding or (lambda _product_id: None)

    def get_feed(
        self, params: PageParams, filters: ProductFilters, q: str | None = None
    ) -> FeedResponse:
        if (
            filters.store_id is not None
            and self.stores.get_by_id(filters.store_id) is None
        ):
            raise NotFound("Loja não encontrada.", code=ErrorCode.STORE_NOT_FOUND)

        rows, total = self.repository.get_active_feed(params, filters, q=q)

        if not rows and (q or filters.applied()):
            return self._sem_resultado(params, filters, q)

        return FeedResponse(
            items=[ProductFeedItemResponse.from_row(row) for row in rows],
            page=params.page,
            page_size=params.page_size,
            total=total,
            applied_filters=filters.applied(),
        )

    def _sem_resultado(
        self, params: PageParams, filters: ProductFilters, q: str | None
    ) -> FeedResponse:
        """Filtro ou busca sem correspondencia: devolve pecas alternativas.

        Relaxa um passo de cada vez, do mais proximo ao mais distante:

        1. busca textual: cada palavra do termo isoladamente ("jaqueta jeans"
           vira "jaqueta" e depois "jeans"), mantendo os filtros;
        2. busca textual: o catalogo sem o termo, mantendo os filtros. Quem
           busca "xyz" em calcas ve calcas, nao o catalogo inteiro;
        3. o catalogo sem filtro nenhum. So aqui um filtro sem resultado (ex.:
           cidade sem peca) passa a mostrar alguma coisa.

        Catalogo vazio devolve vazio, sem erro.
        """
        rows: list[ProductFeedRow] = []
        if q:
            for palavra in self._palavras(q):
                rows, _ = self.repository.get_active_feed(params, filters, q=palavra)
                if rows:
                    return self._alternativas(params, filters, q, rows)
            rows, _ = self.repository.get_active_feed(params, filters)

        if not rows and filters.applied():
            rows, _ = self.repository.get_active_feed(params, ProductFilters())
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
        q: str | None,
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
                reason=(
                    f'Nenhum resultado para "{q}". Veja outras peças disponíveis.'
                    if q
                    else "Nenhum resultado para os filtros selecionados. "
                    "Veja outras peças disponíveis."
                ),
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

    def search_by_image(
        self,
        foto: ArquivoRecebido,
        filters: ProductFilters,
        params: PageParams,
        pessoa: str,
    ) -> ProductImageSearchResponse:
        """Busca por foto: análise -> texto -> vetor -> peças parecidas (#255).

        A foto **não é gravada**: ela passa pela análise do provedor, vira
        texto com os atributos lidos e esse texto vira o vetor da consulta.
        Nenhum armazenamento de mídia é tocado.

        A cota é a mesma do chat (back-end#258), com o assunto próprio: são
        duas chamadas ao provedor por busca, no mesmo orçamento diário.

        Sem filtro, `find_similar` nunca devolve lista vazia enquanto houver
        peça ativa com vetor (RN-61). Com filtro que não casa, a busca
        relaxa os filtros como o chat; se nem assim houver peça com vetor
        (catálogo sem backfill), devolve o catálogo, e não lista vazia.
        """
        tipo = _validar_foto(foto)

        try:
            provider = get_ai_provider()
            modelo = modelo_de_embedding()
        except AIProviderError as exc:
            logger.exception("Provedor de IA indisponível para a busca por foto")
            raise ServiceUnavailable(
                _BUSCA_INDISPONIVEL, code=ErrorCode.AI_UNAVAILABLE
            ) from exc

        self._reservar_busca(pessoa)

        try:
            analise = provider.analyze_image_bytes([ImagePhoto(foto.conteudo, tipo)])
        except AIProviderError as exc:
            logger.exception("Falha ao analisar a foto da busca")
            raise ServiceUnavailable(
                _BUSCA_INDISPONIVEL, code=ErrorCode.AI_UNAVAILABLE
            ) from exc

        texto = texto_da_foto(analise)
        if not texto:
            # A IA respondeu e não reconheceu nada. Sem texto não há vetor,
            # e inventar um seria apresentar ruído como semelhança.
            return self._catalogo_como_resultado(params, filters, analise)

        try:
            vetores = provider.embed([texto])
        except AIProviderError as exc:
            logger.exception("Falha ao gerar o vetor da busca por foto")
            raise ServiceUnavailable(
                _BUSCA_INDISPONIVEL, code=ErrorCode.AI_UNAVAILABLE
            ) from exc
        if not vetores:
            logger.error("Provedor não devolveu vetor para a busca por foto")
            raise ServiceUnavailable(_BUSCA_INDISPONIVEL, code=ErrorCode.AI_UNAVAILABLE)

        rows, total = self._similares(vetores[0], modelo, params, filters)
        if not rows:
            return self._catalogo_como_resultado(params, filters, analise)
        return ProductImageSearchResponse(
            items=[
                ProductImageSearchItem.from_row(row, distance=row["distance"])
                for row in rows
            ],
            interpreted=_interpretada(analise),
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def _reservar_busca(self, pessoa: str) -> None:
        """Conta a busca na cota diária do provedor, com o assunto da rota."""
        try:
            self.quota.reservar(pessoa, assunto="buscas por foto")
        except CotaEsgotada as cota:
            logger.info("Cota da busca por foto esgotada (%s): %s", cota.escopo, pessoa)
            raise AppError(
                cota.mensagem,
                code=ErrorCode.QUOTA_EXCEEDED,
                status_code=429,
            ) from cota

    def _similares(
        self,
        vetor: Sequence[float],
        modelo: str,
        params: PageParams,
        filters: ProductFilters,
    ) -> tuple[list[ProductSimilarRow], int]:
        """As mais próximas que passam nos filtros; sem elas, relaxa.

        O filtro corta por E com a semelhança; se não sobra nada, o mesmo
        caminho do chat: primeiro só a categoria, depois o catálogo inteiro.
        RN-61: filtro sem peça não pode virar "não encontrado".
        """
        rows, total = self.repository.find_similar(vetor, modelo, params, filters)
        if rows or not filters.applied():
            return rows, total
        for relaxado in _relaxamentos(filters):
            rows, total = self.repository.find_similar(vetor, modelo, params, relaxado)
            if rows:
                return rows, total
        return rows, total

    def _catalogo_como_resultado(
        self,
        params: PageParams,
        filters: ProductFilters,
        analise: ImageAnalysisResult,
    ) -> ProductImageSearchResponse:
        """O catálogo no lugar de lista vazia (RN-61), com `distance` nula.

        Dois casos chegam aqui: a IA não reconheceu nada na foto (sem texto,
        sem vetor) ou nenhuma peça tem vetor do modelo ativo. `distance`
        fica nula porque não houve comparação — zero seria dizer "idêntica".
        """
        rows, total = self.repository.get_active_feed(params, filters)
        if not rows and filters.applied():
            rows, total = self.repository.get_active_feed(params, ProductFilters())
        return ProductImageSearchResponse(
            items=[ProductImageSearchItem.from_row(row) for row in rows],
            interpreted=_interpretada(analise),
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    # `ativo`, `reservado` e `vendido` sao publicos (RN-26); `vendido` precisa
    # continuar, porque o detalhe mostra o selo de vendida, e `reservado` (peca
    # num pedido aberto, #243) abre como ela, porque a RN-44 manda sinalizar, e
    # nao esconder. `rascunho` e `despublicado` nao: o rascunho e o estado
    # anterior a confirmacao do vendedor (RN-50) e nao foi publicado por
    # ninguem, e o despublicado saiu da vitrine de proposito (RN-52). Quem
    # precisa ver o proprio rascunho usa `GET /users/me/products/{id}` (#234),
    # nao esta rota.
    PUBLICOS = frozenset({"ativo", "reservado", "vendido"})

    def get_detail(self, product_id: int) -> ProductDetailResponse:
        product = self.repository.get_detail_by_id(product_id)

        if product is None or product.status not in self.PUBLICOS:
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
            composition=product.composition or "",
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
        _recusar_foto_de_etiqueta(data.images)

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
            composition=data.composition,
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
        if data.images:
            product.ai_status = "pending"
            product.ai_error = None
        self.repository.create(product)
        self.repository.commit()
        if data.images:
            try:
                enqueue_image_analysis(
                    product.id, [image.image_url for image in product.images]
                )
            except ImageAnalysisQueueError:
                # IA é complementar ao cadastro: indisponibilidade da fila
                # registra a falha sem desfazer a peça já persistida.
                product.ai_status = "failed"
                product.ai_error = "Não foi possível agendar a análise de IA."
                self.repository.commit()
        return self._to_response(product)

    def update(
        self, user_id: int, product_id: int, data: ProductDraftUpdate
    ) -> ProductDraftResponse:
        """Edita rascunho ou peça publicada/despublicada; vendida é imutável,
        e reservada também, enquanto o pedido estiver aberto."""
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode ser editada.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status == "reservado":
            # O comprador fechou o pedido com esta peça (back-end#247): editar
            # agora a faria diferente do que ele comprou.
            raise AppError(
                "Peça reservada em um pedido não pode ser editada.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
                status_code=409,
            )
        if product.status != "rascunho" and data.images == []:
            # Publicar exige foto (`publish`); editar não pode desfazer isso.
            raise ValidationError(
                "Peça publicada precisa de ao menos uma foto.",
                fields={"images": "Mantenha ao menos uma foto."},
            )
        _recusar_foto_de_etiqueta(data.images)

        texto_antes = texto_da_peca(product)
        updates = data.model_dump(
            exclude_unset=True, exclude={"images", "ai_corrections"}
        )
        for field, value in updates.items():
            setattr(product, field, value)
        regravar_vetor = False
        if texto_da_peca(product) != texto_antes:
            # O vetor descreve o texto de antes (back-end#245): sai já. A peça
            # ativa ganha o novo em segundo plano; fora do ar, ao publicar.
            apagar_embedding(product)
            if product.status == "ativo":
                pedir_embedding(product)
                regravar_vetor = True

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
        if regravar_vetor:
            self._agendar_embedding(product.id)
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
        # Entra na busca por significado (back-end#245): o vetor é gerado em
        # segundo plano, depois da resposta, como a análise da foto. Republicar
        # uma peça que já tem vetor do modelo ativo não pede outro. Falha da
        # IA não desfaz a publicação (RN-57).
        gerar_vetor = precisa_de_embedding(product)
        if gerar_vetor:
            pedir_embedding(product)
        self.repository.commit()
        if gerar_vetor:
            self._agendar_embedding(product.id)
        return self._to_response(product)

    def _get_owned_publicavel(self, user_id: int, product_id: int) -> Product:
        """Peca do vendedor que pode ir para `ativo`: rascunho ou despublicada.

        Vendida responde com o codigo proprio e nao com o conflito generico
        (RN-53) -- quem chama precisa distinguir "ja esta no ar" de "nao mexe
        mais nesta". Reservada tambem e recusada: esta num pedido aberto.
        """
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode mudar de situação.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status == "reservado":
            # Peça num pedido aberto (RN-46): voltar para `ativo` a poria no
            # feed e no carrinho de outra pessoa enquanto o pedido corre.
            raise AppError(
                "Peça reservada em um pedido não pode mudar de situação.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
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
            composition=product.composition,
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
        """Peças do vendedor; sem filtro, sem rascunho (RN-51).

        O rascunho entra só quando é pedido (`status=rascunho`), que é o que a
        aba de rascunhos do painel faz (back-end#271). Ele é cadastro pela
        metade, e não peça em gestão de saldo: misturá-lo à lista de anunciadas
        e vendidas faria a contagem do painel mentir.
        """
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

        O corte é em UTC, como todo datetime deste projeto (`utcnow_naive`).
        Para um produto do RS isso desloca a fronteira do mês em três horas: uma
        venda de 30/09 às 21:30 BRT é 01/10 em UTC e cai no resumo de outubro.
        Enquanto não houver fuso na base, a alternativa seria converter aqui só
        para esta conta, e uma conversão isolada mente sobre o resto.
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
        if product.status == "reservado":
            # Recusa explícita, e não pelo `!= "ativo"` abaixo: publicar e
            # despublicar tratam a peça reservada da mesma forma.
            raise AppError(
                "Peça reservada em um pedido não pode mudar de situação.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
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

    def discard_draft(self, user_id: int, product_id: int) -> None:
        """Apaga o rascunho do vendedor, com as fotos e as correções da IA (#271).

        Descartar é apagar: o rascunho nunca foi público e não tem histórico a
        preservar. A RN-52, que manda despublicar sem apagar, vale para o
        anúncio que já esteve no ar — não para cadastro abandonado.

        Peça em qualquer outra situação é recusada: vendida responde
        `PRODUCT_SOLD` (RN-53) e as demais `PRODUCT_NOT_EDITABLE`. Peça de outro
        vendedor responde 404 pela regra do `_get_owned`, sem confirmar que o id
        existe.
        """
        product = self._get_owned(user_id, product_id)
        if product.status == "vendido":
            raise AppError(
                "Peça vendida não pode ser descartada.",
                code=ErrorCode.PRODUCT_SOLD,
                status_code=409,
            )
        if product.status != "rascunho":
            raise AppError(
                "Só peça em rascunho pode ser descartada.",
                code=ErrorCode.PRODUCT_NOT_EDITABLE,
                status_code=409,
            )
        self.repository.delete(product)
        self.repository.commit()


def _validar_foto(foto: ArquivoRecebido) -> str:
    """Tipo normalizado da foto da busca, ou o erro do contrato (#255).

    Os limites são os de `media_rules`, os mesmos da análise de anúncio,
    mas os status são os da busca: 415 para tipo e 413 para tamanho, como
    o comprovante (back-end#249). A rota genérica de mídia continua 422.
    """
    tipo = (foto.content_type or "").split(";")[0].strip().lower()
    if tipo not in media_rules.ALLOWED_PHOTO_TYPES:
        raise AppError(
            "A busca aceita fotos em JPEG, PNG, WebP ou HEIC.",
            code=ErrorCode.IMAGE_INVALID_TYPE,
            status_code=415,
        )
    if not foto.conteudo:
        raise ValidationError("A foto da busca está vazia.")
    if len(foto.conteudo) > media_rules.MAX_BYTES_PER_FILE:
        raise AppError(
            "A foto passa do limite de "
            f"{media_rules.MAX_BYTES_PER_FILE // (1024 * 1024)}MiB.",
            code=ErrorCode.IMAGE_TOO_LARGE,
            status_code=413,
        )
    return tipo


def _interpretada(analise: ImageAnalysisResult) -> InterpretedPhotoResponse:
    """O que a análise leu da foto, no formato da resposta (RN-58).

    Só o que a IA devolveu: marca vazia quando não havia etiqueta legível,
    como na sugestão de anúncio. É o que faz a busca parecer inteligente em
    vez de mágica — o mesmo princípio dos chips do chat.
    """
    return InterpretedPhotoResponse(
        category=analise.category.value if analise.category else "",
        color=analise.color.value if analise.color else "",
        brand=analise.brand.value if analise.brand else "",
    )


def _relaxamentos(filtros: ProductFilters) -> list[ProductFilters]:
    """Do mais próximo do pedido ao catálogo inteiro.

    Mesma ordem do chat (`AssistantController._relaxamentos`): primeiro só
    a categoria, porque quem filtrou "Calças" prefere outras calças a uma
    jaqueta; depois o catálogo sem filtro, que é o último passo do feed.
    """
    passos = []
    if filtros.category and len(filtros.applied()) > 1:
        passos.append(ProductFilters(category=filtros.category))
    passos.append(ProductFilters())
    return passos


def _recusar_foto_de_etiqueta(images: list[str] | None) -> None:
    """A foto da etiqueta não entra na galeria da peça (back-end#257).

    Ela existe para a IA ler marca, tamanho e composição. Na galeria, apareceria
    na vitrine como foto do produto, e contaria para a foto que publicar exige
    (RN-47): uma peça só com a etiqueta poderia ir ao ar.
    """
    if images and any(media_rules.e_foto_de_etiqueta(url) for url in images):
        raise ValidationError(
            "A foto da etiqueta não entra na galeria da peça.",
            fields={"images": "Envie só fotos da peça; a etiqueta vai à parte."},
        )
