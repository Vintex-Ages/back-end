"""Números gerais da plataforma para a administradora (back-end#269).

O cenário tem duas lojas e três pedidos confirmados, mais um pedido em análise
que **não** pode entrar na conta: volume e comissão saem do histórico de
pagamento (RN-22), e só pedido confirmado é venda (RN-21).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, TypeVar

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.controllers.admin_dashboard_controller import AdminDashboardController
from app.core.clock import utcnow_naive
from app.models import Order, Product, ProductImage, Seller, Store, User

PAINEL = "/api/admin/dashboard"
T = TypeVar("T")


def make_user(db: Session, name: str, email: str, *, is_admin: bool = False) -> User:
    user = User(
        name=name,
        email=email,
        password_hash="not-a-real-password",
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def make_store(db: Session, name: str, dona: str, documento: str) -> Store:
    store = Store(
        name=name,
        pix_key=f"{name.lower().replace(' ', '.')}@pix",
        seller=Seller(
            user=make_user(db, dona, f"{documento}@loja.test"),
            document_type="CPF",
            document_value=documento,
        ),
    )
    db.add(store)
    db.flush()
    return store


def make_product(
    db: Session, store: Store, name: str, price: str = "100.00", status: str = "ativo"
) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal(price),
        status=status,
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


def make_order(
    db: Session, store: Store, buyer: User, *, status: str = "confirmado", amount: str
) -> Order:
    """Pedido com os valores gravados na criação, como o checkout grava (RN-11)."""
    bruto = Decimal(amount)
    order = Order(
        buyer_id=buyer.id,
        store_id=store.id,
        status=status,
        product_amount=bruto,
        commission_rate=Decimal("0.09"),
        platform_fee=(bruto * Decimal("0.09")).quantize(Decimal("0.01")),
        total_amount=bruto,
        expires_at=utcnow_naive() + timedelta(days=3),
        delivery_street="Rua dos Andradas",
        delivery_number="100",
        delivery_city="Porto Alegre",
        delivery_state="RS",
        delivery_zip_code="90020000",
    )
    db.add(order)
    db.flush()
    return order


@pytest.fixture
def cenario(db_session, auth_headers):
    aurora = make_store(db_session, "Brechó Aurora", "Marina Oliveira", "52998224725")
    garimpo = make_store(db_session, "Garimpo do Sul", "Rafael Menezes", "11144477735")
    ana = make_user(db_session, "Ana Souza", "ana@test.local")
    admin = make_user(db_session, "Admin", "admin@test.local", is_admin=True)
    make_product(db_session, aurora, "Jaqueta", "100.00")
    make_product(db_session, aurora, "Bolsa", "80.00")
    make_product(db_session, garimpo, "Saia", "50.00")
    # Não conta em "peças ativas": rascunho ainda não foi publicado.
    make_product(db_session, aurora, "Vestido", "70.00", status="rascunho")
    make_order(db_session, aurora, ana, amount="100.00")
    make_order(db_session, aurora, ana, amount="80.00")
    make_order(db_session, garimpo, ana, amount="50.00")
    # Comprovante ainda em análise: não é venda confirmada e fica fora da conta.
    make_order(db_session, garimpo, ana, status="em_analise", amount="999.00")
    db_session.commit()
    return {
        "admin": admin,
        "ana": ana,
        "db": db_session,
        "loja_aurora": aurora.id,
        "loja_garimpo": garimpo.id,
        "headers": auth_headers(admin.id, is_admin=True),
        "ana_headers": auth_headers(ana.id),
    }


def contar_selects(db: Session, acao: Callable[[], T]) -> tuple[T, list[str]]:
    """Executa a ação e devolve as consultas SQL que ela disparou."""
    consultas: list[str] = []

    def registrar(
        conn: Any, cursor: Any, statement: str, *_: Any
    ) -> None:  # noqa: ANN401
        consultas.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", registrar)
    try:
        resultado = acao()
    finally:
        event.remove(bind, "before_cursor_execute", registrar)
    return resultado, consultas


def test_numeros_com_duas_lojas_e_tres_pedidos(cenario, client):
    response = client.get(PAINEL, headers=cenario["headers"])

    assert response.status_code == 200
    corpo = response.json()
    # Dois vendedores, a compradora e a administradora.
    assert corpo["stores_count"] == 2
    assert corpo["users_count"] == 4
    # Três peças `ativo`; o rascunho fica fora.
    assert corpo["active_products_count"] == 3
    # 100 + 80 + 50; o pedido em análise (999) não entra.
    assert corpo["sales_volume"] == 230.0
    # 9% de cada venda confirmada, como gravado no pedido (RN-11).
    assert corpo["commission_total"] == 20.7
    assert corpo["sales_by_store"] == [
        {
            "store_id": cenario["loja_aurora"],
            "store_name": "Brechó Aurora",
            "amount": 180.0,
        },
        {
            "store_id": cenario["loja_garimpo"],
            "store_name": "Garimpo do Sul",
            "amount": 50.0,
        },
    ]


def test_plataforma_sem_venda_devolve_zero(cenario, client):
    """Plataforma nova não é erro: zero com rótulo e lista vazia."""
    db = cenario["db"]
    db.query(Order).delete()
    db.commit()

    response = client.get(PAINEL, headers=cenario["headers"])

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["sales_volume"] == 0.0
    assert corpo["commission_total"] == 0.0
    assert corpo["sales_by_store"] == []
    # As contagens continuam valendo: há lojas, usuários e peças ativas.
    assert corpo["stores_count"] == 2
    assert corpo["active_products_count"] == 3


def test_sem_sessao_responde_401(client):
    response = client.get(PAINEL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_usuario_comum_responde_403(cenario, client):
    """O dono da peça também não entra: a área é da administradora (RN-32)."""
    response = client.get(PAINEL, headers=cenario["ana_headers"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_painel_sai_em_poucas_consultas(cenario, db_session):
    """Duas idas ao banco: as contagens e as vendas agrupadas por loja."""
    resposta, consultas = contar_selects(
        db_session, lambda: AdminDashboardController(db_session).summary()
    )

    selects = [sql for sql in consultas if sql.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2
    assert resposta.sales_volume == Decimal("230.00")
