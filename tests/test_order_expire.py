"""Expiração do pedido sem comprovante dentro do prazo (back-end#280)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.core.clock import utcnow_naive
from app.models import (
    Order,
    OrderStatusHistory,
    Product,
    ProductImage,
    Seller,
    Store,
    User,
)
from app.repositories.product_repository import ProductRepository
from app.schemas.order_schema import OrderCreate

ENDERECO = {
    "zip_code": "90020000",
    "street": "Rua dos Andradas",
    "number": "100",
    "city": "Porto Alegre",
    "state": "RS",
}


def make_user(db: Session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    db.add(user)
    db.flush()
    return user


def make_product(db: Session, store: Store, name: str) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal("100.00"),
        status="ativo",
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


def pedir(db: Session, buyer: User, *products: Product) -> Order:
    """Cria o pedido pelo caminho de verdade, que já reserva as peças."""
    data = OrderCreate(
        product_ids=[product.id for product in products],
        delivery_address=ENDERECO,
    )
    response = OrderController(db).create(buyer.id, data)
    return db.get(Order, response.id)


def vencer(db: Session, order: Order) -> None:
    """Põe o prazo no passado, como se os 3 dias já tivessem passado."""
    order.expires_at = utcnow_naive() - timedelta(minutes=1)
    db.commit()


def historico(db: Session, order: Order) -> list[str]:
    stmt = (
        select(OrderStatusHistory.status)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.id)
    )
    return list(db.scalars(stmt))


def status_de(db: Session, *rows: Order | Product) -> list[str]:
    for row in rows:
        db.refresh(row)
    return [row.status for row in rows]


@pytest.fixture
def cenario(db_session):
    """Uma compradora e a loja Aurora com três peças à venda."""
    buyer = make_user(db_session, "compradora@test.local")
    aurora = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=make_user(db_session, "aurora@loja.test"),
            document_type="CPF",
            document_value="11111111111",
        ),
    )
    db_session.add(aurora)
    db_session.flush()
    pecas = {
        nome: make_product(db_session, aurora, nome)
        for nome in ("Jaqueta", "Saia", "Bolsa")
    }
    db_session.commit()
    return {"buyer": buyer, **pecas}


def test_pedido_vencido_vira_expirado_com_linha_no_historico(db_session, cenario):
    pedido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"])
    vencer(db_session, pedido)

    assert OrderController(db_session).expire_overdue() == 1

    assert status_de(db_session, pedido) == ["expirado"]
    assert historico(db_session, pedido) == ["aguardando_comprovante", "expirado"]


def test_pecas_do_pedido_expirado_voltam_a_ativo_e_podem_ser_compradas(
    db_session, cenario
):
    pedido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"], cenario["Saia"])
    vencer(db_session, pedido)

    OrderController(db_session).expire_overdue()

    assert status_de(db_session, cenario["Jaqueta"], cenario["Saia"]) == [
        "ativo",
        "ativo",
    ]
    outra = make_user(db_session, "outra@test.local")
    db_session.commit()
    novo = pedir(db_session, outra, cenario["Jaqueta"])
    assert novo.status == "aguardando_comprovante"


def test_pedido_no_prazo_nao_e_alterado(db_session, cenario):
    """Com um vencido e um no prazo juntos, só o vencido muda, e só as peças
    dele são liberadas."""
    vencido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"])
    no_prazo = pedir(db_session, cenario["buyer"], cenario["Saia"])
    vencer(db_session, vencido)

    assert OrderController(db_session).expire_overdue() == 1

    assert status_de(db_session, no_prazo) == ["aguardando_comprovante"]
    assert historico(db_session, no_prazo) == ["aguardando_comprovante"]
    assert status_de(db_session, cenario["Saia"]) == ["reservado"]


def test_pedido_em_analise_nao_expira(db_session, cenario):
    """O comprovante já foi enviado: quem decide é a administradora (RN-21)."""
    pedido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"])
    pedido.status = "em_analise"
    vencer(db_session, pedido)

    assert OrderController(db_session).expire_overdue() == 0

    assert status_de(db_session, pedido) == ["em_analise"]
    assert status_de(db_session, cenario["Jaqueta"]) == ["reservado"]


def test_rodar_duas_vezes_nao_muda_nada_na_segunda(db_session, cenario):
    pedido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"])
    vencer(db_session, pedido)
    controller = OrderController(db_session)

    assert controller.expire_overdue() == 1
    assert controller.expire_overdue() == 0

    assert historico(db_session, pedido) == ["aguardando_comprovante", "expirado"]
    assert status_de(db_session, cenario["Jaqueta"]) == ["ativo"]


def test_falha_ao_liberar_as_pecas_nao_expira_o_pedido(
    db_session, cenario, monkeypatch
):
    """Pedido e peças mudam no mesmo commit: se liberar as peças falha, o
    pedido também volta, e nada fica pela metade."""
    pedido = pedir(db_session, cenario["buyer"], cenario["Jaqueta"])
    vencer(db_session, pedido)

    def falha(self, order_ids):
        raise RuntimeError("falha simulada ao liberar as peças")

    monkeypatch.setattr(ProductRepository, "release_for_orders", falha)

    with pytest.raises(RuntimeError):
        OrderController(db_session).expire_overdue()

    assert status_de(db_session, pedido) == ["aguardando_comprovante"]
    assert historico(db_session, pedido) == ["aguardando_comprovante"]
    assert status_de(db_session, cenario["Jaqueta"]) == ["reservado"]
