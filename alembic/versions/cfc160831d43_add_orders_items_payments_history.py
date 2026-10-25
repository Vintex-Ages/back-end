"""add orders, order_items, payments, order_status_history

Revision ID: cfc160831d43
Revises: a7c91e4b5d02
Create Date: 2026-10-12

As quatro tabelas da compra numa migration só (back-end#243), mais
`reservado` no CHECK de `products.status`.

Os status ficam escritos aqui, e não importados de `app.models`: a migration
descreve o banco daquela revisão e não pode mudar quando o model mudar.

O downgrade devolve peça `reservado` para `ativo` antes de recriar o CHECK
antigo. Sem isso, num banco com pedido aberto, o `CREATE CONSTRAINT` falha
porque já existe linha fora da lista.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "cfc160831d43"
down_revision: Union[str, None] = "a7c91e4b5d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_STATUS_CHECK = (
    "status IN ('aguardando_comprovante', 'em_analise', 'confirmado', "
    "'preparando', 'enviado', 'concluido', 'expirado')"
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
    ]


def upgrade() -> None:
    op.drop_constraint("ck_products_status", "products", type_="check")
    op.create_check_constraint(
        "ck_products_status",
        "products",
        "status IN ('rascunho', 'ativo', 'reservado', 'vendido', 'despublicado')",
    )

    op.create_table(
        "orders",
        sa.Column("buyer_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="aguardando_comprovante",
            nullable=False,
        ),
        sa.Column("product_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("platform_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("delivery_street", sa.String(length=150), nullable=False),
        sa.Column("delivery_number", sa.String(length=20), nullable=False),
        sa.Column("delivery_complement", sa.String(length=100), nullable=True),
        sa.Column("delivery_neighborhood", sa.String(length=100), nullable=True),
        sa.Column("delivery_city", sa.String(length=100), nullable=False),
        sa.Column("delivery_state", sa.String(length=2), nullable=False),
        sa.Column("delivery_zip_code", sa.String(length=10), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(ORDER_STATUS_CHECK, name="ck_orders_status"),
        sa.CheckConstraint(
            "product_amount >= 0 AND platform_fee >= 0 AND total_amount >= 0",
            name="ck_orders_amounts",
        ),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_orders_commission_rate",
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "store_id", name="uq_orders_id_store"),
    )
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"])
    op.create_index("ix_orders_store_id", "orders", ["store_id"])
    op.create_index("ix_orders_status_expires_at", "orders", ["status", "expires_at"])

    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["order_id", "store_id"],
            ["orders.id", "orders.store_id"],
            name="fk_order_items_order_store",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id", "product_id", name="uq_order_items_order_product"
        ),
    )
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    op.create_table(
        "payments",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pendente", nullable=False
        ),
        sa.Column("receipt_key", sa.String(length=255), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("validated_by_id", sa.BigInteger(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pendente', 'aprovado', 'rejeitado')",
            name="ck_payments_status",
        ),
        sa.CheckConstraint(
            "(status = 'pendente'"
            " AND validated_by_id IS NULL AND validated_at IS NULL)"
            " OR (status <> 'pendente'"
            " AND validated_by_id IS NOT NULL AND validated_at IS NOT NULL)",
            name="ck_payments_validation",
        ),
        sa.CheckConstraint(
            "(status = 'rejeitado' AND rejection_reason IS NOT NULL)"
            " OR (status <> 'rejeitado' AND rejection_reason IS NULL)",
            name="ck_payments_rejection_reason",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["validated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])

    op.create_table(
        "order_status_history",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(ORDER_STATUS_CHECK, name="ck_order_status_history_status"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_status_history_order_id", "order_status_history", ["order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")

    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")

    op.drop_index("ix_order_items_product_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_status_expires_at", table_name="orders")
    op.drop_index("ix_orders_store_id", table_name="orders")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_table("orders")

    op.execute("UPDATE products SET status = 'ativo' WHERE status = 'reservado'")
    op.drop_constraint("ck_products_status", "products", type_="check")
    op.create_check_constraint(
        "ck_products_status",
        "products",
        "status IN ('rascunho', 'ativo', 'vendido', 'despublicado')",
    )
