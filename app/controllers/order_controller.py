import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.controllers.media_controller import ArquivoRecebido
from app.core.clock import utcnow_naive
from app.core.comissao import COMISSAO_VINTEX, dividir
from app.core.errors import AppError, Conflict, ErrorCode, NotFound, ValidationError
from app.core.pagination import Page, PageParams
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.product import Product
from app.repositories.order_repository import OrderRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.order_schema import (
    DeliveryAddress,
    OrderCreate,
    OrderHistoryResponse,
    OrderItemResponse,
    OrderListItemResponse,
    OrderListPaymentResponse,
    OrderListStoreResponse,
    OrderPaymentResponse,
    OrderReceiptResponse,
    OrderResponse,
    OrderStoreResponse,
)
from app.services import media_rules
from app.services.media_storage import MediaStorage

logger = logging.getLogger(__name__)

# Prazo para o comprovante ser aprovado. Vencido, o pedido expira e a peça
# volta a `ativo` (back-end#243).
PRAZO_DO_COMPROVANTE = timedelta(days=3)
_STATUS_INICIAL = "aguardando_comprovante"


class OrderController:
    """Criação do pedido a partir das peças de uma loja (back-end#247).

    Um pedido é de uma loja só: o comprador paga o preço cheio direto na chave
    Pix do vendedor (RN-19 e RN-20), então cada loja vira um pedido. A
    comissão de 9% (RN-11) sai do lado do vendedor: `platform_fee` é
    informação, e `total_amount` é igual a `product_amount`.

    O pedido nasce em `aguardando_comprovante` e nada aqui o avança (RN-21).
    """

    def __init__(self, db: Session):
        self.orders = OrderRepository(db)
        self.products = ProductRepository(db)

    def create(self, user_id: int, data: OrderCreate) -> OrderResponse:
        products = self.products.get_many_for_order(data.product_ids)
        # Id que não existe responde igual a peça fora de venda: para quem
        # compra, as duas são "esta peça não está disponível".
        if len(products) != len(data.product_ids) or any(
            product.status != "ativo" for product in products
        ):
            raise self._indisponivel()

        if len({product.store_id for product in products}) > 1:
            raise Conflict(
                "Um pedido só pode ter peças de uma loja.",
                code=ErrorCode.MIXED_STORES,
            )

        store = products[0].store
        if not store.pix_key:
            # Sem a chave o comprador não tem como pagar: melhor falhar aqui do
            # que gerar um pedido impagável.
            raise Conflict(
                "Esta loja ainda não cadastrou uma chave Pix.",
                code=ErrorCode.STORE_WITHOUT_PIX,
            )

        # A conferência acima só dá a mensagem certa no caso comum. A garantia
        # contra duas pessoas na mesma peça é o UPDATE condicional: se outra
        # compra reservou alguma entre a leitura e aqui, nada é gravado.
        if self.products.reserve(data.product_ids) != len(data.product_ids):
            self.orders.rollback()
            raise self._indisponivel()

        order = self.orders.create(self._novo_pedido(user_id, products, data))
        self.orders.commit()
        return self._to_response(order)

    def expire_overdue(self) -> int:
        """Expira os pedidos sem comprovante dentro do prazo e devolve as peças
        a `ativo` (back-end#280). Devolve quantos pedidos expiraram.

        Só `aguardando_comprovante` expira: em `em_analise` o comprovante já
        foi enviado e quem decide é a administradora (RN-21).

        Pedido e peças mudam no mesmo commit: não pode existir pedido expirado
        com peça presa, nem peça liberada com pedido aberto. Rodar de novo não
        muda nada, porque o pedido já não está aguardando e a peça já não está
        reservada. Qualquer gatilho (rotina periódica, chamada antes de outra
        operação) deve passar por aqui.
        """
        try:
            expired_ids = self.orders.expire_overdue(utcnow_naive())
            self.products.release_for_orders(expired_ids)
        except Exception:
            self.orders.rollback()
            raise
        self.orders.commit()
        return len(expired_ids)

    def list_mine(
        self, user_id: int, params: PageParams
    ) -> Page[OrderListItemResponse]:
        """ "Meus pedidos", mais recente primeiro (back-end#248)."""
        orders, total = self.orders.list_for_buyer(user_id, params)
        agora = utcnow_naive()
        return Page[OrderListItemResponse](
            items=[_item_da_lista(order, agora) for order in orders],
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def get_mine(self, user_id: int, order_id: int) -> OrderResponse:
        """Detalhe do pedido de quem pede (back-end#248). Pedido de outra
        pessoa responde 404, igual a inexistente: um 403 confirmaria o id."""
        order = self.orders.get_for_buyer(order_id, user_id)
        if order is None:
            raise NotFound("Pedido não encontrado.", code=ErrorCode.ORDER_NOT_FOUND)
        return self._to_response(order)

    def submit_receipt(
        self,
        user_id: int,
        order_id: int,
        arquivo: ArquivoRecebido,
        storage: MediaStorage,
    ) -> OrderReceiptResponse:
        """Recebe o comprovante do Pix e põe o pedido em análise (back-end#249).

        Serve para o primeiro envio e para o reenvio depois de uma rejeição,
        que devolve o pedido a `aguardando_comprovante` (RN-23). Reenviar cria
        um pagamento novo e não apaga o anterior (RN-22).

        Quem avança o pedido daqui em diante é a administradora (RN-21).
        """
        order = self.orders.get_for_buyer(order_id, user_id)
        if order is None:
            raise NotFound("Pedido não encontrado.", code=ErrorCode.ORDER_NOT_FOUND)

        agora = utcnow_naive()
        if order.status == _STATUS_INICIAL and order.expires_at <= agora:
            # Venceu e ninguém expirou ainda: não há rotina periódica, e o
            # `expire_overdue` pede para ser chamado antes de outra operação.
            # Comprovante fora do prazo não entra; as peças voltam à venda.
            self.expire_overdue()
            raise self._nao_aguarda_comprovante()
        if order.status != _STATUS_INICIAL:
            raise self._nao_aguarda_comprovante()

        content_type = _validar_comprovante(arquivo)
        key = storage.upload("receipt", arquivo.conteudo, content_type)
        try:
            # Condicional como as outras transições: dois envios ao mesmo
            # tempo, só o primeiro encontra `aguardando_comprovante`.
            if not self.orders.transition(
                order_id, de=_STATUS_INICIAL, para="em_analise"
            ):
                raise self._nao_aguarda_comprovante()
            self.orders.add_payment(
                Payment(
                    order_id=order_id,
                    receipt_key=key,
                    receipt_name=_nome_do_arquivo(arquivo.nome),
                    receipt_content_type=content_type,
                )
            )
            self.orders.commit()
        except Exception:
            self.orders.rollback()
            # O arquivo já subiu: sem a linha que aponta para ele, vira objeto
            # órfão no bucket. Falha ao apagar não esconde o erro original.
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001
                logger.warning("Comprovante órfão no storage: %s", key)
            raise

        enviado = self.orders.get_for_buyer(order_id, user_id)
        payment = _comprovante(enviado) if enviado is not None else None
        if enviado is None or payment is None:
            raise RuntimeError(f"Pedido {order_id} sumiu logo depois do envio.")
        # Só a etapa que o envio criou, como no contrato: a resposta é parcial,
        # e o histórico inteiro está no detalhe.
        nova_etapa = enviado.status_history[-1]
        return OrderReceiptResponse(
            id=enviado.id,
            status=enviado.status,
            payment=payment,
            history=[
                OrderHistoryResponse(status=nova_etapa.status, at=nova_etapa.changed_at)
            ],
        )

    @staticmethod
    def _nao_aguarda_comprovante() -> Conflict:
        return Conflict(
            "Este pedido não está aguardando comprovante.",
            code=ErrorCode.ORDER_NOT_AWAITING_RECEIPT,
        )

    @staticmethod
    def _indisponivel() -> Conflict:
        return Conflict(
            "Alguma peça do pedido não está mais disponível.",
            code=ErrorCode.PIECE_UNAVAILABLE,
        )

    @staticmethod
    def _novo_pedido(user_id: int, products: list[Product], data: OrderCreate) -> Order:
        bruto = sum((product.price for product in products), Decimal("0"))
        comissao, _ = dividir(bruto)
        endereco = data.delivery_address
        store_id = products[0].store_id
        return Order(
            buyer_id=user_id,
            store_id=store_id,
            status=_STATUS_INICIAL,
            product_amount=bruto,
            commission_rate=COMISSAO_VINTEX,
            platform_fee=comissao,
            total_amount=bruto,
            expires_at=utcnow_naive() + PRAZO_DO_COMPROVANTE,
            delivery_street=endereco.street,
            delivery_number=endereco.number,
            delivery_complement=endereco.complement,
            delivery_neighborhood=endereco.neighborhood,
            delivery_city=endereco.city,
            delivery_state=endereco.state,
            delivery_zip_code=endereco.zip_code,
            # Nome, preço e capa são cópia: o pedido continua mostrando o que
            # foi comprado mesmo se a peça for editada depois.
            items=[
                OrderItem(
                    store_id=store_id,
                    product_id=product.id,
                    name=product.name,
                    price=product.price,
                    cover_image_url=(
                        product.images[0].image_url if product.images else None
                    ),
                )
                for product in products
            ],
            status_history=[OrderStatusHistory(status=_STATUS_INICIAL)],
        )

    @staticmethod
    def _to_response(order: Order) -> OrderResponse:
        status, history = _linha_do_tempo(order, utcnow_naive())
        return OrderResponse(
            id=order.id,
            store=OrderStoreResponse(
                id=order.store.id,
                name=order.store.name,
                pix_key=order.store.pix_key or "",
            ),
            items=[
                OrderItemResponse(
                    product_id=item.product_id,
                    name=item.name,
                    price=item.price,
                    cover_image_url=item.cover_image_url,
                )
                for item in order.items
            ],
            product_amount=order.product_amount,
            platform_fee=order.platform_fee,
            total_amount=order.total_amount,
            status=status,
            history=history,
            delivery_address=_endereco(order),
            payment=_comprovante(order),
            expires_at=order.expires_at,
            created_at=order.created_at,
        )


# Etapas depois de `confirmado`, simuladas: não há transportadora (RN-81 e
# RN-83), então nenhuma rotina grava estas linhas. Cada uma conta como
# atingida um tempo depois da aprovação, e a leitura deriva o que já passou
# (back-end#248). Um dia entre etapas, o mesmo ritmo do mock do front
# (`buildHistory` em `orderService.ts`).
_ETAPAS_SIMULADAS: tuple[tuple[str, timedelta], ...] = (
    ("preparando", timedelta(days=1)),
    ("enviado", timedelta(days=2)),
    ("concluido", timedelta(days=3)),
)


def _linha_do_tempo(
    order: Order, agora: datetime
) -> tuple[str, list[OrderHistoryResponse]]:
    """O status atual e o histórico, com as etapas simuladas já atingidas."""
    history = [
        OrderHistoryResponse(status=entry.status, at=entry.changed_at)
        for entry in order.status_history
    ]
    if order.status != "confirmado":
        return order.status, history

    confirmado_em = max(
        entry.changed_at
        for entry in order.status_history
        if entry.status == "confirmado"
    )
    status = order.status
    for etapa, depois in _ETAPAS_SIMULADAS:
        atingida_em = confirmado_em + depois
        if atingida_em > agora:
            break
        history.append(OrderHistoryResponse(status=etapa, at=atingida_em))
        status = etapa
    return status, history


def status_atual(order: Order, agora: datetime) -> str:
    """O status que o comprador vê, com as etapas simuladas. Quem precisa
    saber se o pedido já foi entregue (`concluido`, back-end#267) pergunta
    aqui, e não a `orders.status`, que para em `confirmado`."""
    status, _ = _linha_do_tempo(order, agora)
    return status


def _validar_comprovante(arquivo: ArquivoRecebido) -> str:
    """Tipo normalizado do comprovante, ou o erro que o front espera.

    As regras são as de `media_rules` (imagem ou PDF, 8 MiB), mas os status
    não: aqui o contrato é 415 para tipo e 413 para tamanho (back-end#249),
    que o front traduz em mensagens próprias. A rota genérica de mídia
    continua respondendo 422.
    """
    tipo = (arquivo.content_type or "").split(";")[0].strip().lower()
    if tipo not in media_rules.ALLOWED_RECEIPT_TYPES:
        raise AppError(
            "O comprovante deve ser uma imagem ou um PDF.",
            code=ErrorCode.RECEIPT_INVALID_TYPE,
            status_code=415,
        )
    if not arquivo.conteudo:
        raise ValidationError("O arquivo do comprovante está vazio.")
    if len(arquivo.conteudo) > media_rules.MAX_BYTES_PER_FILE:
        raise AppError(
            f"O comprovante passa do limite de "
            f"{media_rules.MAX_BYTES_PER_FILE // (1024 * 1024)}MiB.",
            code=ErrorCode.RECEIPT_TOO_LARGE,
            status_code=413,
        )
    return tipo


def _nome_do_arquivo(nome: str) -> str:
    """O nome que o comprador vê no pedido, sem caminho e cabendo na coluna.

    Navegador antigo manda `C:\\fakepath\\comprovante.pdf`; o que interessa é
    só o último pedaço.
    """
    base = nome.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base[:255] or "comprovante"


def _comprovante(order: Order) -> OrderPaymentResponse | None:
    """O comprovante vigente: o envio mais recente. Reenviar não apaga o
    anterior (RN-22), mas é o último que o comprador acompanha."""
    if not order.payments:
        return None
    payment = order.payments[-1]
    return OrderPaymentResponse(
        status=payment.status,
        # Da coluna gravada no envio (back-end#244), nunca a chave do storage.
        receipt_name=payment.receipt_name,
        submitted_at=payment.submitted_at,
        rejection_reason=payment.rejection_reason,
    )


def _endereco(order: Order) -> DeliveryAddress:
    return DeliveryAddress(
        zip_code=order.delivery_zip_code,
        street=order.delivery_street,
        number=order.delivery_number,
        complement=order.delivery_complement,
        neighborhood=order.delivery_neighborhood,
        city=order.delivery_city,
        state=order.delivery_state,
    )


def _item_da_lista(order: Order, agora: datetime) -> OrderListItemResponse:
    status, _ = _linha_do_tempo(order, agora)
    comprovante = _comprovante(order)
    return OrderListItemResponse(
        id=order.id,
        store=OrderListStoreResponse(id=order.store.id, name=order.store.name),
        items=[
            OrderItemResponse(
                product_id=item.product_id,
                name=item.name,
                price=item.price,
                cover_image_url=item.cover_image_url,
            )
            for item in order.items
        ],
        total_amount=order.total_amount,
        status=status,
        payment=(
            OrderListPaymentResponse(status=comprovante.status) if comprovante else None
        ),
        delivery_address=_endereco(order),
        created_at=order.created_at,
    )
