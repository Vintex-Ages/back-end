"""Lista e detalhe dos pedidos do comprador (back-end#248)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.controllers.payment_review_controller import PaymentReviewController
from app.core.clock import utcnow_naive
from app.models import (
    Order,
    OrderStatusHistory,
    Payment,
    Product,
    ProductImage,
    Seller,
    Store,
    User,
)
from app.schemas.order_schema import OrderCreate

ENDERECO = {
    "zip_code": "90020000",
    "street": "Rua dos Andradas",
    "number": "100",
    "complement": "ap 302",
    "neighborhood": "Centro Histórico",
    "city": "Porto Alegre",
    "state": "RS",
}


def make_user(db: Session, email: str, *, is_admin: bool = False) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash="not-a-real-password",
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def make_product(
    db: Session, store: Store, name: str, price: str = "100.00"
) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal(price),
        status="ativo",
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


def pedir(db: Session, buyer: User, *products: Product) -> Order:
    resposta = OrderController(db).create(
        buyer.id,
        OrderCreate(product_ids=[p.id for p in products], delivery_address=ENDERECO),
    )
    return db.get(Order, resposta.id)


def enviar_comprovante(db: Session, order: Order) -> None:
    """O que a rota de envio (#249) vai gravar."""
    order.status = "em_analise"
    db.add(OrderStatusHistory(order_id=order.id, status="em_analise"))
    db.add(Payment(order_id=order.id, receipt_key=f"payments/receipts/{order.id}"))
    db.commit()


def aprovado_ha(db: Session, order: Order, admin: User, tempo: timedelta) -> None:
    """Aprova pelo caminho de verdade e recua a data da aprovação."""
    enviar_comprovante(db, order)
    PaymentReviewController(db).approve(order.id, admin)
    linha = db.scalar(
        select(OrderStatusHistory).where(
            OrderStatusHistory.order_id == order.id,
            OrderStatusHistory.status == "confirmado",
        )
    )
    linha.changed_at = utcnow_naive() - tempo
    db.commit()


@contextmanager
def contar_consultas(db: Session) -> Iterator[list[str]]:
    consultas: list[str] = []

    def registrar(conn, cursor, statement, *args) -> None:
        consultas.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        yield consultas
    finally:
        event.remove(engine, "before_cursor_execute", registrar)


@pytest.fixture
def cenario(db_session, auth_headers):
    aurora = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=make_user(db_session, "aurora@loja.test"),
            document_type="CPF",
            document_value="52998224725",
        ),
    )
    db_session.add(aurora)
    db_session.flush()
    pecas = [make_product(db_session, aurora, n) for n in ("Jaqueta", "Saia", "Bolsa")]
    compradora = make_user(db_session, "compradora@test.local")
    outra = make_user(db_session, "outra@test.local")
    admin = make_user(db_session, "admin@test.local", is_admin=True)
    db_session.commit()
    return {
        "pecas": pecas,
        "compradora": compradora,
        "outra": outra,
        "admin": admin,
        "como_compradora": auth_headers(compradora.id),
        "como_outra": auth_headers(outra.id),
    }


def listar(client, headers, **params):
    return client.get("/api/users/me/orders", headers=headers, params=params)


def detalhar(client, headers, order_id: int):
    return client.get(f"/api/users/me/orders/{order_id}", headers=headers)


# --- lista -----------------------------------------------------------------------


def test_lista_so_os_pedidos_de_quem_pede_mais_recente_primeiro(
    client, db_session, cenario
):
    jaqueta, saia, bolsa = cenario["pecas"]
    primeiro = pedir(db_session, cenario["compradora"], jaqueta)
    segundo = pedir(db_session, cenario["compradora"], saia)
    pedir(db_session, cenario["outra"], bolsa)

    response = listar(client, cenario["como_compradora"])

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [segundo.id, primeiro.id]
    assert body["total"] == 2


def test_lista_e_paginada(client, db_session, cenario):
    jaqueta, saia, _ = cenario["pecas"]
    pedir(db_session, cenario["compradora"], jaqueta)
    mais_recente = pedir(db_session, cenario["compradora"], saia)

    body = listar(client, cenario["como_compradora"], page=1, page_size=1).json()

    assert (body["page"], body["page_size"], body["total"]) == (1, 1, 2)
    assert [item["id"] for item in body["items"]] == [mais_recente.id]


def test_lista_nao_traz_chave_pix_nem_historico_e_traz_o_endereco(
    client, db_session, cenario
):
    pedir(db_session, cenario["compradora"], cenario["pecas"][0])

    item = listar(client, cenario["como_compradora"]).json()["items"][0]

    assert "pix_key" not in item["store"]
    assert "history" not in item
    # É daqui que o checkout pré-preenche a próxima compra.
    assert item["delivery_address"] == ENDERECO
    assert item["payment"] is None
    assert item["status"] == "aguardando_comprovante"


def test_lista_vazia_nao_e_erro(client, cenario):
    body = listar(client, cenario["como_compradora"]).json()

    assert body["items"] == []
    assert body["total"] == 0


def test_lista_nao_faz_uma_consulta_por_pedido(client, db_session, cenario):
    jaqueta, saia, bolsa = cenario["pecas"]
    pedir(db_session, cenario["compradora"], jaqueta)
    with contar_consultas(db_session) as com_um:
        listar(client, cenario["como_compradora"])

    pedir(db_session, cenario["compradora"], saia)
    pedir(db_session, cenario["compradora"], bolsa)
    with contar_consultas(db_session) as com_tres:
        listar(client, cenario["como_compradora"])

    assert len(com_tres) == len(com_um)


# --- detalhe ---------------------------------------------------------------------


def test_detalhe_traz_chave_pix_valores_e_historico(client, db_session, cenario):
    pedido = pedir(db_session, cenario["compradora"], *cenario["pecas"][:2])

    response = detalhar(client, cenario["como_compradora"], pedido.id)

    assert response.status_code == 200
    body = response.json()
    assert body["store"] == {
        "id": pedido.store_id,
        "name": "Aurora",
        "pix_key": "aurora@pix",
    }
    assert [h["status"] for h in body["history"]] == ["aguardando_comprovante"]
    assert all(h["at"] for h in body["history"])
    assert body["expires_at"]
    assert body["payment"] is None


def test_valores_saem_como_numero(client, db_session, cenario):
    pedido = pedir(db_session, cenario["compradora"], *cenario["pecas"][:2])

    detalhe = detalhar(client, cenario["como_compradora"], pedido.id).json()
    item = listar(client, cenario["como_compradora"]).json()["items"][0]

    for valor in (
        detalhe["product_amount"],
        detalhe["platform_fee"],
        detalhe["total_amount"],
        detalhe["items"][0]["price"],
        item["total_amount"],
        item["items"][0]["price"],
    ):
        assert isinstance(valor, float), valor
    assert detalhe["total_amount"] == 200.0
    assert detalhe["platform_fee"] == 18.0


def test_pedido_de_outra_pessoa_responde_404(client, db_session, cenario):
    pedido = pedir(db_session, cenario["outra"], cenario["pecas"][0])

    response = detalhar(client, cenario["como_compradora"], pedido.id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_pedido_inexistente_responde_404(client, cenario):
    assert detalhar(client, cenario["como_compradora"], 999_999).status_code == 404


@pytest.mark.parametrize("caminho", ["/api/users/me/orders", "/api/users/me/orders/1"])
def test_sem_token_responde_401(client, caminho):
    assert client.get(caminho).status_code == 401


# --- comprovante e linha do tempo ------------------------------------------------


def test_comprovante_em_analise_aparece_na_lista_e_no_detalhe(
    client, db_session, cenario
):
    pedido = pedir(db_session, cenario["compradora"], cenario["pecas"][0])
    enviar_comprovante(db_session, pedido)

    detalhe = detalhar(client, cenario["como_compradora"], pedido.id).json()
    item = listar(client, cenario["como_compradora"]).json()["items"][0]

    assert detalhe["status"] == "em_analise"
    assert detalhe["payment"]["status"] == "pendente"
    assert detalhe["payment"]["submitted_at"]
    # Nome do arquivo só existe a partir da #244; a URL nunca vem.
    assert detalhe["payment"]["receipt_name"] is None
    assert "receipt_url" not in detalhe["payment"]
    assert item["payment"] == {"status": "pendente"}


def test_pedido_rejeitado_traz_o_motivo(client, db_session, cenario):
    pedido = pedir(db_session, cenario["compradora"], cenario["pecas"][0])
    enviar_comprovante(db_session, pedido)
    PaymentReviewController(db_session).reject(
        pedido.id, cenario["admin"], "Valor diferente do pedido."
    )

    detalhe = detalhar(client, cenario["como_compradora"], pedido.id).json()

    assert detalhe["status"] == "aguardando_comprovante"
    assert detalhe["payment"]["status"] == "rejeitado"
    assert detalhe["payment"]["rejection_reason"] == "Valor diferente do pedido."


@pytest.mark.parametrize(
    "aprovado_ha_tanto, status, etapas_derivadas",
    [
        (timedelta(hours=1), "confirmado", []),
        (timedelta(days=1, hours=1), "preparando", ["preparando"]),
        (timedelta(days=2, hours=1), "enviado", ["preparando", "enviado"]),
        (timedelta(days=10), "concluido", ["preparando", "enviado", "concluido"]),
    ],
)
def test_etapas_depois_de_confirmado_sao_derivadas_na_leitura(
    client, db_session, cenario, aprovado_ha_tanto, status, etapas_derivadas
):
    pedido = pedir(db_session, cenario["compradora"], cenario["pecas"][0])
    aprovado_ha(db_session, pedido, cenario["admin"], aprovado_ha_tanto)

    detalhe = detalhar(client, cenario["como_compradora"], pedido.id).json()
    item = listar(client, cenario["como_compradora"]).json()["items"][0]

    assert detalhe["status"] == status
    assert item["status"] == status
    assert [h["status"] for h in detalhe["history"]] == [
        "aguardando_comprovante",
        "em_analise",
        "confirmado",
        *etapas_derivadas,
    ]
    # Nada foi gravado para as etapas derivadas.
    db_session.refresh(pedido)
    assert pedido.status == "confirmado"
    assert len(pedido.status_history) == 3
