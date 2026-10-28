"""A administradora aprova ou rejeita o comprovante (back-end#251).

O envio do comprovante é a #249, que ainda não existe. Aqui ele é simulado por
`enviar_comprovante`, que grava o que a rota de envio vai gravar: o pedido em
`em_analise`, a linha no histórico e um pagamento `pendente`.
"""

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


def enviar_comprovante(db: Session, order: Order) -> Payment:
    """O que a rota de envio (#249) grava: em análise, com pagamento pendente."""
    order.status = "em_analise"
    db.add(OrderStatusHistory(order_id=order.id, status="em_analise"))
    payment = Payment(order_id=order.id, receipt_key=f"payments/receipts/{order.id}")
    db.add(payment)
    db.commit()
    return payment


def historico(db: Session, order: Order) -> list[str]:
    stmt = (
        select(OrderStatusHistory.status)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.id)
    )
    return list(db.scalars(stmt))


@pytest.fixture
def cenario(db_session, auth_headers):
    """Compradora com um pedido em análise de duas peças da loja Aurora."""
    vendedora = make_user(db_session, "aurora@loja.test")
    aurora = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=vendedora, document_type="CPF", document_value="52998224725"
        ),
    )
    db_session.add(aurora)
    db_session.flush()
    jaqueta = make_product(db_session, aurora, "Jaqueta")
    saia = make_product(db_session, aurora, "Saia")
    compradora = make_user(db_session, "compradora@test.local")
    admin = make_user(db_session, "admin@test.local", is_admin=True)
    db_session.commit()

    resposta = OrderController(db_session).create(
        compradora.id,
        OrderCreate(product_ids=[jaqueta.id, saia.id], delivery_address=ENDERECO),
    )
    pedido = db_session.get(Order, resposta.id)
    enviar_comprovante(db_session, pedido)
    return {
        "pedido": pedido,
        "pecas": [jaqueta, saia],
        "compradora": compradora,
        "vendedora": vendedora,
        "admin": admin,
        "como_admin": auth_headers(admin.id, is_admin=True),
        "como_compradora": auth_headers(compradora.id),
    }


def aprovar(client, cenario, order_id: int | None = None):
    order_id = cenario["pedido"].id if order_id is None else order_id
    return client.post(
        f"/api/admin/payments/{order_id}/approve", headers=cenario["como_admin"]
    )


def rejeitar(client, cenario, reason: object = "Comprovante ilegível."):
    return client.post(
        f"/api/admin/payments/{cenario['pedido'].id}/reject",
        headers=cenario["como_admin"],
        json={"reason": reason},
    )


# --- aprovar ---------------------------------------------------------------------


def test_aprovar_confirma_o_pedido_e_grava_quem_e_quando(client, db_session, cenario):
    response = aprovar(client, cenario)

    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == cenario["pedido"].id
    assert body["status"] == "confirmado"
    assert body["payment"]["status"] == "aprovado"
    assert body["payment"]["validated_by"] == {
        "id": cenario["admin"].id,
        "name": cenario["admin"].name,
    }
    assert body["payment"]["validated_at"]
    assert "rejection_reason" not in body["payment"]

    pedido = cenario["pedido"]
    db_session.refresh(pedido)
    assert pedido.status == "confirmado"
    pagamento = pedido.payments[-1]
    assert (pagamento.status, pagamento.validated_by_id) == (
        "aprovado",
        cenario["admin"].id,
    )


def test_aprovar_vende_as_pecas_e_elas_contam_no_resumo_da_vendedora(
    client, db_session, cenario, auth_headers
):
    aprovar(client, cenario)

    for peca in cenario["pecas"]:
        db_session.refresh(peca)
        assert peca.status == "vendido"
        assert peca.sold_at is not None

    resumo = client.get(
        "/api/users/me/sales/summary?period=month",
        headers=auth_headers(cenario["vendedora"].id),
    )
    assert resumo.json()["sold_count"] == 2
    assert resumo.json()["gross"] == 200.0


# --- rejeitar --------------------------------------------------------------------


def test_rejeitar_devolve_o_pedido_com_o_motivo(client, db_session, cenario):
    response = rejeitar(client, cenario, "  Valor diferente do pedido.  ")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "aguardando_comprovante"
    assert body["payment"]["status"] == "rejeitado"
    assert body["payment"]["rejection_reason"] == "Valor diferente do pedido."
    assert body["payment"]["validated_by"]["id"] == cenario["admin"].id

    for peca in cenario["pecas"]:
        db_session.refresh(peca)
        assert peca.status == "reservado", "a compradora ainda vai reenviar"


def test_rejeitar_renova_o_prazo_e_a_expiracao_nao_leva_o_pedido(
    client, db_session, cenario
):
    """Comprovante enviado no fim do prazo e rejeitado depois dele: sem renovar,
    a rotina da #280 expiraria o pedido antes do reenvio que a RN-23 promete."""
    pedido = cenario["pedido"]
    pedido.expires_at = utcnow_naive() - timedelta(hours=1)
    db_session.commit()

    rejeitar(client, cenario)

    db_session.refresh(pedido)
    prazo = pedido.expires_at - utcnow_naive()
    assert timedelta(days=2, hours=23) < prazo <= timedelta(days=3)
    assert OrderController(db_session).expire_overdue() == 0
    db_session.refresh(pedido)
    assert pedido.status == "aguardando_comprovante"


def test_rejeitar_e_reenviar_guarda_os_dois_comprovantes(client, db_session, cenario):
    pedido = cenario["pedido"]
    rejeitar(client, cenario)
    db_session.refresh(pedido)

    enviar_comprovante(db_session, pedido)
    segunda = aprovar(client, cenario)

    assert segunda.status_code == 200
    db_session.refresh(pedido)
    assert [p.status for p in pedido.payments] == ["rejeitado", "aprovado"]
    assert pedido.payments[0].rejection_reason == "Comprovante ilegível."


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_motivo_vazio_responde_422_e_nada_muda(client, db_session, cenario, motivo):
    response = rejeitar(client, cenario, motivo)

    assert response.status_code == 422
    db_session.refresh(cenario["pedido"])
    assert cenario["pedido"].status == "em_analise"
    assert cenario["pedido"].payments[-1].status == "pendente"


# --- histórico e conflitos -------------------------------------------------------


def test_historico_mostra_as_transicoes_com_data(client, db_session, cenario):
    pedido = cenario["pedido"]
    rejeitar(client, cenario)
    db_session.refresh(pedido)
    enviar_comprovante(db_session, pedido)
    aprovar(client, cenario)

    assert historico(db_session, pedido) == [
        "aguardando_comprovante",
        "em_analise",
        "aguardando_comprovante",
        "em_analise",
        "confirmado",
    ]
    assert all(entry.changed_at for entry in pedido.status_history)


@pytest.mark.parametrize(
    "primeira, segunda",
    [("approve", "approve"), ("reject", "reject"), ("approve", "reject")],
)
def test_segunda_validacao_responde_409(client, cenario, primeira, segunda):
    def validar(acao: str):
        return client.post(
            f"/api/admin/payments/{cenario['pedido'].id}/{acao}",
            headers=cenario["como_admin"],
            json={"reason": "Motivo."},
        )

    assert validar(primeira).status_code == 200
    response = validar(segunda)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_IN_REVIEW"


def test_pedido_sem_comprovante_enviado_responde_409(client, db_session, cenario):
    pedido = cenario["pedido"]
    pedido.status = "aguardando_comprovante"
    db_session.commit()

    assert aprovar(client, cenario).status_code == 409


def test_pedido_inexistente_responde_404(client, cenario):
    response = aprovar(client, cenario, order_id=999_999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


@pytest.mark.parametrize("acao", ["approve", "reject"])
def test_compradora_responde_403_e_nada_muda(client, db_session, cenario, acao):
    response = client.post(
        f"/api/admin/payments/{cenario['pedido'].id}/{acao}",
        headers=cenario["como_compradora"],
        json={"reason": "Motivo."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"
    db_session.refresh(cenario["pedido"])
    assert cenario["pedido"].status == "em_analise"
