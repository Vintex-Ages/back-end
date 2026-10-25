"""Tabelas da compra: pedido, item, pagamento e histórico (back-end#243).

Os testes marcados com `postgres` rodam contra o banco migrado pelo Alembic, e
não pelo `create_all`: é a migration que está sendo testada, e o SQLite dos
testes padrão não liga FK sem `PRAGMA foreign_keys`.
"""

import os
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    Product,
    Seller,
    Store,
    User,
)

RAIZ = Path(__file__).resolve().parents[1]
REVISAO_ANTERIOR = "a7c91e4b5d02"
TABELAS_DO_PEDIDO = ("orders", "order_items", "payments", "order_status_history")


def criar_usuario(db: Session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    db.add(user)
    db.flush()
    return user


def criar_loja(db: Session, nome: str, documento: str) -> Store:
    store = Store(
        name=nome,
        seller=Seller(
            user=criar_usuario(db, f"{documento}@loja.test"),
            document_type="CPF",
            document_value=documento,
        ),
    )
    db.add(store)
    db.flush()
    return store


def criar_peca(db: Session, store: Store, status: str = "ativo") -> Product:
    product = Product(
        store=store, name="Jaqueta", price=Decimal("100.00"), status=status
    )
    db.add(product)
    db.flush()
    return product


def criar_pedido(db: Session, comprador: User, store: Store) -> Order:
    order = Order(
        buyer_id=comprador.id,
        store_id=store.id,
        product_amount=Decimal("100.00"),
        commission_rate=Decimal("0.0900"),
        platform_fee=Decimal("9.00"),
        total_amount=Decimal("100.00"),
        expires_at=datetime(2026, 10, 15, 12, 0),
        delivery_street="Rua dos Andradas",
        delivery_number="100",
        delivery_city="Porto Alegre",
        delivery_state="RS",
        delivery_zip_code="90020000",
    )
    db.add(order)
    db.flush()
    return order


def criar_item(db: Session, order: Order, product: Product, store_id: int) -> OrderItem:
    item = OrderItem(
        order_id=order.id,
        store_id=store_id,
        product_id=product.id,
        name=product.name,
        price=product.price,
    )
    db.add(item)
    db.flush()
    return item


# --- products.status (SQLite: o CHECK vale nos dois bancos) -----------------


def test_products_status_aceita_reservado(db_session: Session) -> None:
    store = criar_loja(db_session, "Brechó Aurora", "11111111111")

    product = criar_peca(db_session, store, status="reservado")

    assert product.status == "reservado"


def test_products_status_recusa_valor_fora_da_lista(db_session: Session) -> None:
    store = criar_loja(db_session, "Brechó Aurora", "11111111111")

    with pytest.raises(IntegrityError, match="ck_products_status"):
        criar_peca(db_session, store, status="no_carrinho")


# --- pedido, item, pagamento e histórico (Postgres migrado) ------------------


@pytest.fixture
def cenario(pg_session: Session) -> dict:
    comprador = criar_usuario(pg_session, "compradora@test.local")
    aurora = criar_loja(pg_session, "Brechó Aurora", "11111111111")
    brisa = criar_loja(pg_session, "Brechó Brisa", "22222222222")
    return {
        "comprador": comprador,
        "aurora": aurora,
        "brisa": brisa,
        "pedido": criar_pedido(pg_session, comprador, aurora),
        "peca": criar_peca(pg_session, aurora, status="reservado"),
        "admin": criar_usuario(pg_session, "admin@test.local"),
    }


@pytest.mark.postgres
def test_pedido_completo_grava_item_pagamento_e_historico(
    pg_session: Session, cenario: dict
) -> None:
    pedido = cenario["pedido"]
    criar_item(pg_session, pedido, cenario["peca"], cenario["aurora"].id)
    pg_session.add_all(
        [
            Payment(order_id=pedido.id, receipt_key="payments/receipts/a.jpg"),
            OrderStatusHistory(order_id=pedido.id, status="aguardando_comprovante"),
        ]
    )
    pg_session.flush()
    pg_session.refresh(pedido)

    assert pedido.status == "aguardando_comprovante"
    assert [item.product_id for item in pedido.items] == [cenario["peca"].id]
    assert pedido.payments[0].status == "pendente"
    assert pedido.payments[0].submitted_at is not None
    assert [h.status for h in pedido.status_history] == ["aguardando_comprovante"]


@pytest.mark.postgres
def test_item_de_outra_loja_nao_entra_no_pedido(
    pg_session: Session, cenario: dict
) -> None:
    peca_da_brisa = criar_peca(pg_session, cenario["brisa"])

    with pytest.raises(IntegrityError, match="fk_order_items_order_store"):
        criar_item(pg_session, cenario["pedido"], peca_da_brisa, cenario["brisa"].id)


@pytest.mark.postgres
def test_mesma_peca_nao_entra_duas_vezes_no_pedido(
    pg_session: Session, cenario: dict
) -> None:
    pedido, peca, loja = cenario["pedido"], cenario["peca"], cenario["aurora"]
    criar_item(pg_session, pedido, peca, loja.id)

    with pytest.raises(IntegrityError, match="uq_order_items_order_product"):
        criar_item(pg_session, pedido, peca, loja.id)


@pytest.mark.postgres
def test_status_do_pedido_recusa_valor_fora_da_lista(
    pg_session: Session, cenario: dict
) -> None:
    cenario["pedido"].status = "cancelado"

    with pytest.raises(IntegrityError, match="ck_orders_status"):
        pg_session.flush()


@pytest.mark.postgres
def test_historico_recusa_status_fora_da_lista(
    pg_session: Session, cenario: dict
) -> None:
    pg_session.add(
        OrderStatusHistory(order_id=cenario["pedido"].id, status="cancelado")
    )

    with pytest.raises(IntegrityError, match="ck_order_status_history_status"):
        pg_session.flush()


@pytest.mark.postgres
def test_reenviar_comprovante_cria_registro_novo(
    pg_session: Session, cenario: dict
) -> None:
    pedido = cenario["pedido"]
    rejeitado = Payment(
        order_id=pedido.id,
        receipt_key="payments/receipts/primeiro.jpg",
        status="rejeitado",
        rejection_reason="Valor diferente do pedido.",
        validated_by_id=cenario["admin"].id,
        validated_at=datetime(2026, 10, 13, 9, 0),
    )
    pg_session.add(rejeitado)
    pg_session.flush()

    pg_session.add(
        Payment(order_id=pedido.id, receipt_key="payments/receipts/segundo.jpg")
    )
    pg_session.flush()
    pg_session.refresh(pedido)

    assert [(p.receipt_key, p.status) for p in pedido.payments] == [
        ("payments/receipts/primeiro.jpg", "rejeitado"),
        ("payments/receipts/segundo.jpg", "pendente"),
    ]
    assert pedido.payments[0].rejection_reason == "Valor diferente do pedido."
    assert pedido.payments[0].validated_by_id == cenario["admin"].id
    assert pedido.payments[0].validated_at == datetime(2026, 10, 13, 9, 0)


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("campos", "constraint"),
    [
        # Rejeição sem motivo (RN-23).
        (
            {"status": "rejeitado", "validated": True},
            "ck_payments_rejection_reason",
        ),
        # Motivo em comprovante que não foi rejeitado.
        (
            {"status": "aprovado", "validated": True, "rejection_reason": "x"},
            "ck_payments_rejection_reason",
        ),
        # Aprovado sem saber quem validou e quando.
        ({"status": "aprovado"}, "ck_payments_validation"),
        # Pendente que já tem validador.
        ({"status": "pendente", "validated": True}, "ck_payments_validation"),
        ({"status": "estornado", "validated": True}, "ck_payments_status"),
    ],
)
def test_pagamento_recusa_validacao_incoerente(
    pg_session: Session, cenario: dict, campos: dict, constraint: str
) -> None:
    campos = dict(campos)
    if campos.pop("validated", False):
        campos["validated_by_id"] = cenario["admin"].id
        campos["validated_at"] = datetime(2026, 10, 13, 9, 0)

    with pytest.raises(IntegrityError, match=constraint):
        pg_session.add(
            Payment(
                order_id=cenario["pedido"].id,
                receipt_key="payments/receipts/a.jpg",
                **campos,
            )
        )
        pg_session.flush()


@pytest.mark.postgres
def test_pedido_recusa_valor_negativo(pg_session: Session, cenario: dict) -> None:
    cenario["pedido"].platform_fee = Decimal("-1.00")

    with pytest.raises(IntegrityError, match="ck_orders_amounts"):
        pg_session.flush()


# --- cadeia de migrations ----------------------------------------------------


def _alembic(comando: str, revisao: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", comando, revisao],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": os.environ["TEST_POSTGRES_URL"]},
        check=True,
    )


@pytest.mark.postgres
@pytest.mark.skipif(
    os.environ.get("TEST_POSTGRES_REUSE_MIGRATED_DB") == "1",
    reason="desce migration: só roda em banco de teste descartável",
)
def test_migration_desce_e_sobe_com_peca_reservada(pg_engine: Engine) -> None:
    """Sobe e desce a revisão do #243 com uma peça `reservado` no banco.

    O job `Migrations` do CI já sobe e desce a cadeia num banco vazio. Este
    teste cobre o que ele não cobre: sem o `UPDATE` do downgrade, recriar o
    CHECK antigo falha por causa da peça reservada.
    """
    with pg_engine.begin() as conn:
        user_id = conn.scalar(
            text(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES ('Migra', 'migra@test.local', 'x') RETURNING id"
            )
        )
        seller_id = conn.scalar(
            text(
                "INSERT INTO sellers (user_id, document_type, document_value) "
                "VALUES (:u, 'CPF', '99999999999') RETURNING id"
            ),
            {"u": user_id},
        )
        store_id = conn.scalar(
            text(
                "INSERT INTO stores (seller_id, name) VALUES (:s, 'Migra') RETURNING id"
            ),
            {"s": seller_id},
        )
        product_id = conn.scalar(
            text(
                "INSERT INTO products (store_id, name, price, quantity, status) "
                "VALUES (:s, 'Peça', 10, 1, 'reservado') RETURNING id"
            ),
            {"s": store_id},
        )
    pg_engine.dispose()

    try:
        _alembic("downgrade", REVISAO_ANTERIOR)
        with pg_engine.connect() as conn:
            tabelas = set(inspect(conn).get_table_names())
            status = conn.scalar(
                text("SELECT status FROM products WHERE id = :id"), {"id": product_id}
            )
        assert tabelas.isdisjoint(TABELAS_DO_PEDIDO)
        assert status == "ativo"
    finally:
        pg_engine.dispose()
        _alembic("upgrade", "head")
        with pg_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM products WHERE id = :id"), {"id": product_id}
            )
            conn.execute(text("DELETE FROM stores WHERE id = :id"), {"id": store_id})
            conn.execute(text("DELETE FROM sellers WHERE id = :id"), {"id": seller_id})
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    with pg_engine.connect() as conn:
        tabelas = set(inspect(conn).get_table_names())
    assert tabelas.issuperset(TABELAS_DO_PEDIDO)
