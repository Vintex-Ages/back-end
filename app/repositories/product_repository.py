import operator
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from functools import reduce
from typing import TypedDict, cast

from sqlalchemy import ScalarSelect, Select, case, func, literal, select, update
from sqlalchemy.orm import Session, joinedload, selectinload, with_expression
from sqlalchemy.sql.elements import ColumnElement

from app.core.pagination import Page, PageParams, paginate
from app.models.address import Address
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.schemas.product_management_schema import ProductManagementResponse
from app.schemas.product_schema import ProductFilters

# Mesma expressao do indice ix_products_search_trgm (migration 0f9a7f647244).
# Se mudar aqui sem mudar la, o Postgres para de usar o indice e a busca vira
# varredura da tabela inteira.
TEXTO_BUSCAVEL = func.immutable_unaccent(
    func.lower(
        func.coalesce(Product.name, "")
        + " "
        + func.coalesce(Product.description, "")
        + " "
        + func.coalesce(Product.brand, "")
        + " "
        + func.coalesce(Product.category, "")
    )
)


class ProductFeedRow(TypedDict):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str
    store_id: int
    store_name: str
    store_verified: bool


class ProductSimilarRow(ProductFeedRow):
    """Linha do feed mais a distância de cosseno até o vetor da busca
    (back-end#246): 0 é idêntica, e quanto maior, menos parecida."""

    distance: float


def _cover_image_url() -> ScalarSelect[str | None]:
    """Subquery da capa: a foto de menor posição da peça. Correlacionada com o
    `Product` da consulta externa, então vem na mesma consulta da listagem,
    sem uma consulta por peça (#86)."""
    return (
        select(ProductImage.image_url)
        .where(ProductImage.product_id == Product.id)
        .order_by(ProductImage.position.asc(), ProductImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )


def _feed_select() -> Select[tuple[object, ...]]:
    """Base comum a qualquer listagem de peça (feed, busca) — o resultado
    sempre bate com `ProductFeedRow`, incluindo a subquery da capa. Quem
    chama ainda adiciona `join`/`where`/`order_by` próprios."""
    # Selo "Confiável" (#143): subquery pelo `Store` que o chamador já juntou,
    # para ninguém precisar lembrar de um join extra com `Seller`.
    store_verified = (
        select(Seller.verified).where(Seller.id == Store.seller_id).scalar_subquery()
    )
    return select(
        Product.id,
        Product.name,
        Product.price,
        _cover_image_url().label("cover_image_url"),
        Product.status,
        Store.id.label("store_id"),
        Store.name.label("store_name"),
        store_verified.label("store_verified"),
    )


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_seller(self, product_id: int, user_id: int) -> Product | None:
        """Peça filtrada pelo dono (join `Store` → `Seller`).

        Não existe `get_by_id` sem dono: quem chama sempre sabe quem está
        pedindo (`get_current_user_id`), e um `Product` de outro vendedor
        deve responder igual a "não existe" (`PRODUCT_NOT_FOUND`), nunca
        vazar que a peça existe mas não é dele.
        """
        return self.db.scalar(
            select(Product)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Product.id == product_id, Seller.user_id == user_id)
        )

    def get_active_feed(
        self, params: PageParams, filters: ProductFilters, q: str | None = None
    ) -> tuple[list[ProductFeedRow], int]:
        stmt = (
            _feed_select()
            .join(Store, Store.id == Product.store_id)
            # A localizacao e da loja. O outer join preserva lojas sem endereco
            # quando city/state nao foram informados.
            .outerjoin(Address, Store.address_id == Address.id)
            .where(*self._condicoes_do_catalogo(filters))
            .order_by(Product.created_at.desc(), Product.id.desc())
        )

        if q:
            stmt = stmt.where(
                TEXTO_BUSCAVEL.contains(func.immutable_unaccent(func.lower(q)))
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0
        rows = (
            self.db.execute(stmt.offset(params.offset).limit(params.limit))
            .mappings()
            .all()
        )
        return [cast(ProductFeedRow, dict(row)) for row in rows], total

    def _condicoes_do_catalogo(
        self, filters: ProductFilters
    ) -> list[ColumnElement[bool]]:
        """Peça ativa mais os filtros do catálogo, somados por E lógico.

        Compartilhado pelo feed e pela busca por semelhança (back-end#246),
        para os dois filtrarem do mesmo jeito. Quem chama junta `Store` e,
        por outer join, `Address`.
        """
        conditions: list[ColumnElement[bool]] = [Product.status == "ativo"]
        filter_columns = {
            "category": Product.category,
            "size": Product.size,
            "brand": Product.brand,
            "condition": Product.condition,
            "color": Product.color,
            "city": Address.city,
            "state": Address.state,
        }
        for field_name, column in filter_columns.items():
            value = getattr(filters, field_name)
            if value is not None:
                normalized_column = func.lower(column)
                normalized_value = func.lower(value)
                if self.db.get_bind().dialect.name == "postgresql":
                    normalized_column = func.immutable_unaccent(normalized_column)
                    normalized_value = func.immutable_unaccent(normalized_value)
                conditions.append(normalized_column == normalized_value)
        if filters.price_min is not None:
            conditions.append(Product.price >= filters.price_min)
        if filters.price_max is not None:
            conditions.append(Product.price <= filters.price_max)
        if filters.store_id is not None:
            conditions.append(Store.id == filters.store_id)
        return conditions

    def list_for_seller(
        self, user_id: int, params: PageParams, status: str | None = None
    ) -> Page[ProductManagementResponse]:
        stmt = (
            select(Product)
            # A capa vem na mesma consulta da página (back-end#265). O
            # `populate_existing` porque `with_expression` não preenche peça
            # que a sessão já tenha carregado sem a expressão.
            .options(with_expression(Product.cover_image_url, _cover_image_url()))
            .execution_options(populate_existing=True)
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
        if status is not None:
            stmt = stmt.where(Product.status == status)
        else:
            # RN-51: a área do vendedor é gestão do que está anunciado. O
            # rascunho é cadastro pela metade e não se mistura a ela — só
            # entra quando é pedido (`?status=rascunho`, a aba de rascunhos do
            # painel, back-end#271).
            stmt = stmt.where(Product.status != "rascunho")
        return paginate(
            self.db,
            stmt,
            params,
            item_schema=ProductManagementResponse,
        )

    def sales_summary(
        self, user_id: int, desde: datetime | None
    ) -> tuple[int, Decimal]:
        """`(quantidade, bruto)` das peças vendidas da loja de quem pede.

        `desde=None` é "tudo". Vendedor sem venda no período recebe
        `(0, Decimal("0"))` e não erro (back-end#146).

        Só entram peças com `sold_at` preenchido quando há corte de período:
        peça vendida sem data não pode ser contada num intervalo sem que a
        conta minta. No "tudo" ela entra, porque ali não há intervalo.
        """
        stmt = (
            select(
                func.count(Product.id),
                func.coalesce(func.sum(Product.price), 0),
            )
            .join(Store, Store.id == Product.store_id)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id, Product.status == "vendido")
        )
        if desde is not None:
            stmt = stmt.where(Product.sold_at.is_not(None), Product.sold_at >= desde)
        quantidade, bruto = self.db.execute(stmt).one()
        return int(quantidade), Decimal(bruto)

    def get_store_for_user(self, user_id: int) -> Store | None:
        """Loja de quem está criando/editando — um vendedor, uma loja."""
        stmt = (
            select(Store)
            .join(Seller, Seller.id == Store.seller_id)
            .where(Seller.user_id == user_id)
        )
        return self.db.scalars(stmt).first()

    def find_similar(
        self,
        query_embedding: Sequence[float],
        embedding_model: str,
        params: PageParams,
        filters: ProductFilters | None = None,
    ) -> tuple[list[ProductSimilarRow], int]:
        """Peças ativas mais próximas do vetor da busca, paginadas, e o total
        (BE-US027-3, back-end#149; paginação, filtros e distância na #246).

        - **Só vetores do mesmo modelo** (`embedding_model`): distância entre
          espaços vetoriais de modelos diferentes é ruído com cara de
          resultado. Peça sem embedding, ou de outro modelo, não entra.
        - **Os filtros do catálogo somam por E** com a semelhança, os mesmos
          do feed (`_condicoes_do_catalogo`).
        - **A distância volta em cada linha**, e quem chama decide como
          rotular. Não há limiar aqui dentro: uma busca sem nada parecido
          ainda devolve as mais próximas, e a lista não volta vazia enquanto
          houver catálogo (RN-61).

        Nunca inventa peça: só o que já existe no catálogo real (RN-65).
        """
        distancia = Product.embedding.cosine_distance(list(query_embedding))
        stmt = (
            _feed_select()
            .add_columns(distancia.label("distance"))
            .join(Store, Store.id == Product.store_id)
            .outerjoin(Address, Store.address_id == Address.id)
            .where(
                *self._condicoes_do_catalogo(filters or ProductFilters()),
                Product.embedding.is_not(None),
                Product.embedding_model == embedding_model,
            )
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = (
            self.db.execute(
                stmt.order_by(distancia, Product.id)
                .offset(params.offset)
                .limit(params.limit)
            )
            .mappings()
            .all()
        )
        return [cast(ProductSimilarRow, dict(row)) for row in rows], total

    def vetores_pelo_nome(
        self,
        palavras: Sequence[str],
        embedding_model: str,
        filters: ProductFilters,
        limite: int,
        desempate: Sequence[str] = (),
    ) -> list[Sequence[float]]:
        """Vetores das peças ativas cujo nome mais casa com as palavras
        (back-end#254).

        É o ponto de partida da sugestão de preço sem chamar o provedor de IA:
        a peça que está sendo cadastrada ainda não tem vetor, mas as do
        catálogo têm. Vence quem tem mais palavras do nome em comum; com
        "tênis nike azul", um "Tênis Nike Azul" é referência, e um "Tênis
        Branco" só se nenhum nome tiver mais palavras. Sem acento e sem caixa,
        como a busca textual (RN-41). As palavras já vêm normalizadas.

        `desempate` (as palavras da descrição) só decide entre nomes que casam
        igual: "Jaqueta" com descrição "jeans" prefere a "Jaqueta jeans". Peça
        que só casa pelo desempate não é referência.
        """
        if not palavras:
            return []
        nome = func.immutable_unaccent(func.lower(Product.name))

        def acertos_de(lista: Sequence[str]) -> ColumnElement[int]:
            return reduce(
                operator.add,
                [case((nome.contains(p, autoescape=True), 1), else_=0) for p in lista],
            )

        acertos = acertos_de(palavras)
        # `ORDER BY 0` o Postgres lê como "a coluna da posição 0" e recusa: sem
        # desempate, a ordem não passa por ele.
        extras = acertos_de(desempate) if desempate else literal(0)
        ordem = [acertos.desc(), extras.desc()] if desempate else [acertos.desc()]
        rows = self.db.execute(
            select(
                Product.embedding,
                acertos.label("acertos"),
                extras.label("extras"),
            )
            .join(Store, Store.id == Product.store_id)
            .outerjoin(Address, Store.address_id == Address.id)
            .where(
                *self._condicoes_do_catalogo(filters),
                Product.embedding.is_not(None),
                Product.embedding_model == embedding_model,
                acertos > 0,
            )
            .order_by(*ordem, Product.id)
            .limit(limite)
        ).all()
        if not rows:
            return []
        melhor = (rows[0].acertos, rows[0].extras)
        return [row.embedding for row in rows if (row.acertos, row.extras) == melhor]

    def get_detail_by_id(self, product_id: int) -> Product | None:
        stmt = (
            select(Product)
            .options(
                joinedload(Product.store).joinedload(Store.address),
                joinedload(Product.store).joinedload(Store.seller),
                selectinload(Product.images),
            )
            .where(Product.id == product_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, product_id: int) -> Product | None:
        """Como `get_detail_by_id`, mas com `ai_corrections` — usado pelas
        rotas de peça do vendedor, que devolvem o histórico de correções da IA
        junto com a peça."""
        stmt = (
            select(Product)
            .options(
                joinedload(Product.store).joinedload(Store.address),
                joinedload(Product.store).joinedload(Store.seller),
                selectinload(Product.images),
                selectinload(Product.ai_corrections),
            )
            .where(Product.id == product_id)
        )
        return self.db.scalars(stmt).one_or_none()

    def get_many_for_order(self, product_ids: Sequence[int]) -> list[Product]:
        """Peças do pedido com loja e fotos. Id que não existe não volta: quem
        chama compara a quantidade."""
        stmt = (
            select(Product)
            .options(joinedload(Product.store), selectinload(Product.images))
            .where(Product.id.in_(product_ids))
        )
        return list(self.db.scalars(stmt).unique())

    def reserve(self, product_ids: Sequence[int]) -> int:
        """`ativo -> reservado` num comando só, e devolve quantas mudaram.

        Conferir e trocar no mesmo UPDATE é o que resolve duas pessoas pedindo
        a mesma peça ao mesmo tempo: o banco aplica um UPDATE por vez na linha,
        e o segundo já não encontra `ativo`. Ler o status antes e gravar depois
        deixaria as duas passarem pela conferência.
        """
        result = self.db.execute(
            update(Product)
            .where(Product.id.in_(product_ids), Product.status == "ativo")
            .values(status="reservado")
        )
        return result.rowcount

    def release_for_orders(self, order_ids: Sequence[int]) -> int:
        """`reservado -> ativo` para as peças desses pedidos, e devolve quantas
        mudaram. O caminho de volta do `reserve` (back-end#280)."""
        if not order_ids:
            return 0
        pecas_dos_pedidos = select(OrderItem.product_id).where(
            OrderItem.order_id.in_(order_ids)
        )
        result = self.db.execute(
            update(Product)
            .where(Product.id.in_(pecas_dos_pedidos), Product.status == "reservado")
            .values(status="ativo")
        )
        return result.rowcount

    def sell_for_order(self, order_id: int, sold_at: datetime) -> int:
        """`reservado -> vendido` para as peças do pedido, com a data da venda,
        e devolve quantas mudaram (back-end#251).

        É a aprovação do comprovante que confirma a venda, e não o checkout: a
        partir daqui a peça conta no resumo do vendedor (RN-95), que lê
        `sold_at`.
        """
        pecas_do_pedido = select(OrderItem.product_id).where(
            OrderItem.order_id == order_id
        )
        result = self.db.execute(
            update(Product)
            .where(Product.id.in_(pecas_do_pedido), Product.status == "reservado")
            .values(status="vendido", sold_at=sold_at)
        )
        return result.rowcount

    def create(self, product: Product) -> Product:
        self.db.add(product)
        self.db.flush()
        return product

    def delete(self, product: Product) -> None:
        """Apaga a peça; fotos e correções da IA caem junto (cascade do modelo).

        Só quem decide se a peça pode ser apagada é o controller — aqui é
        persistência. O arquivo da foto não é apagado do storage: a URL veio de
        `/users/me/media` e pode estar em outra peça do mesmo vendedor, então
        apagar o objeto quebraria a outra.
        """
        self.db.delete(product)

    def commit(self) -> None:
        self.db.commit()
