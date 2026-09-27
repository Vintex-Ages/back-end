from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ErrorCode, NotFound
from app.core.pagination import DEFAULT_PAGE_SIZE, Page, PageParams
from app.repositories.cart_repository import CartRepository
from app.repositories.product_repository import ProductFeedRow, ProductRepository
from app.schemas.cart_schema import CartItemResponse, CartStoreResponse
from app.schemas.product_schema import FeedStoreResponse

# Só peça ativa pode ser comprada. Qualquer outro status (hoje, `vendido`)
# fica no carrinho marcado como indisponível e fora do subtotal.
_STATUS_DISPONIVEL = "ativo"

# POST e DELETE devolvem o carrinho atualizado a partir da primeira página,
# com o mesmo tamanho padrão do GET.
_PRIMEIRA_PAGINA = PageParams(page=1, page_size=DEFAULT_PAGE_SIZE)


class CartController:
    """Regras do carrinho do comprador (issue #147).

    O carrinho é agrupado por loja porque o pagamento é Pix direto ao
    vendedor: cada grupo tem um subtotal próprio, que vira um valor exato
    para uma chave Pix no checkout.
    """

    def __init__(self, db: Session):
        self.db = db
        self.cart = CartRepository(db)
        self.products = ProductRepository(db)

    def get_cart(self, user_id: int, params: PageParams) -> Page[CartStoreResponse]:
        total = self.cart.count_stores(user_id)
        store_ids = self.cart.list_store_ids(user_id, params)
        rows = self.cart.list_items_for_stores(user_id, store_ids)
        return Page[CartStoreResponse](
            items=self._group_by_store(store_ids, rows),
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def add_item(self, user_id: int, product_id: int) -> Page[CartStoreResponse]:
        """Idempotente: peça que já está no carrinho devolve o carrinho igual,
        sem erro — o front trata como sucesso."""
        product = self.products.get_detail_by_id(product_id)
        # Despublicada responde como inexistente, igual ao detalhe da peça.
        if product is None or product.status == "despublicado":
            raise NotFound("Produto não encontrado.", code=ErrorCode.PRODUCT_NOT_FOUND)

        if self.cart.get_item(user_id, product_id) is not None:
            return self.get_cart(user_id, _PRIMEIRA_PAGINA)

        if product.status != _STATUS_DISPONIVEL:
            raise Conflict(
                "Esta peça não está mais disponível.",
                code=ErrorCode.PRODUCT_UNAVAILABLE,
            )

        try:
            self.cart.add_item(user_id, product_id)
            self.db.commit()
        except IntegrityError:
            # Corrida: a mesma peça entrou no carrinho entre o check acima e
            # o INSERT (ex.: duplo clique). A unique (user_id, product_id) é a
            # garantia de verdade; se foi isso, o resultado é o mesmo sucesso.
            # Qualquer outra violação (ex.: FK de usuário) segue como erro.
            self.db.rollback()
            if self.cart.get_item(user_id, product_id) is None:
                raise

        return self.get_cart(user_id, _PRIMEIRA_PAGINA)

    def remove_item(self, user_id: int, product_id: int) -> Page[CartStoreResponse]:
        item = self.cart.get_item(user_id, product_id)
        # Item de outro comprador responde igual a "não está no carrinho":
        # a busca já filtra por user_id, então não vaza que ele existe.
        if item is None:
            raise NotFound(
                "Peça não está no carrinho.", code=ErrorCode.CART_ITEM_NOT_FOUND
            )

        self.cart.remove_item(item)
        self.db.commit()
        return self.get_cart(user_id, _PRIMEIRA_PAGINA)

    @staticmethod
    def _group_by_store(
        store_ids: list[int], rows: list[ProductFeedRow]
    ) -> list[CartStoreResponse]:
        """Monta um grupo por loja, na ordem de `store_ids` (a da paginação),
        somando no subtotal só as peças disponíveis."""
        groups: dict[int, CartStoreResponse] = {}
        for row in rows:
            group = groups.get(row["store_id"])
            if group is None:
                group = CartStoreResponse(
                    store=FeedStoreResponse(id=row["store_id"], name=row["store_name"]),
                    items=[],
                    subtotal=Decimal("0"),
                )
                groups[row["store_id"]] = group

            available = row["status"] == _STATUS_DISPONIVEL
            group.items.append(
                CartItemResponse(
                    product_id=row["id"],
                    name=row["name"],
                    price=row["price"],
                    cover_image_url=row["cover_image_url"],
                    status=row["status"],
                    available=available,
                )
            )
            if available:
                group.subtotal += row["price"]

        return [groups[store_id] for store_id in store_ids if store_id in groups]
