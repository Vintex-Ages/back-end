"""Reportar não recebimento ou dano (back-end#268).

O botão aparece do recebimento ou da confirmação em diante (RN-77): aqui,
qualquer status derivado de `confirmado` até `concluido`. Os testes recuam a
data da aprovação no histórico em vez de esperar, que é o que a leitura do
pedido olha.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.models import (
    Order,
    OrderComplaint,
    OrderItem,
    OrderStatusHistory,
    Product,
    Seller,
    Store,
    User,
)

ORDERS_URL = "/api/users/me/orders"
ADMIN_URL = "/api/admin/complaints"
TEXTO = "A caixa chegou aberta e a jaqueta estava rasgada."


def make_user(db: Session, email: str, *, is_admin: bool = False) -> User:
    user = User(name=email, email=email, password_hash="not-a-real", is_admin=is_admin)
    db.add(user)
    db.flush()
    return user


def make_store(db: Session) -> Store:
    store = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=make_user(db, "vendedora@loja.test"),
            document_type="CPF",
            document_value="52998224725",
        ),
    )
    db.add(store)
    db.flush()
    return store


def make_order(
    db: Session,
    buyer: User,
    store: Store,
    *,
    aprovado_ha: timedelta | None = timedelta(hours=1),
) -> Order:
    """`aprovado_ha` é há quanto tempo o comprovante foi aprovado; `None`
    deixa o pedido aguardando comprovante."""
    product = Product(
        store=store, name="Jaqueta", price=Decimal("100.00"), status="vendido"
    )
    db.add(product)
    db.flush()
    agora = utcnow_naive()
    history = [OrderStatusHistory(status="aguardando_comprovante", changed_at=agora)]
    if aprovado_ha is not None:
        history.append(
            OrderStatusHistory(status="confirmado", changed_at=agora - aprovado_ha)
        )
    order = Order(
        buyer_id=buyer.id,
        store_id=store.id,
        status="aguardando_comprovante" if aprovado_ha is None else "confirmado",
        product_amount=Decimal("100.00"),
        commission_rate=Decimal("0.0900"),
        platform_fee=Decimal("9.00"),
        total_amount=Decimal("100.00"),
        expires_at=agora + timedelta(days=3),
        delivery_street="Rua dos Andradas",
        delivery_number="100",
        delivery_city="Porto Alegre",
        delivery_state="RS",
        delivery_zip_code="90020000",
        items=[
            OrderItem(
                store_id=store.id,
                product_id=product.id,
                name=product.name,
                price=product.price,
            )
        ],
        status_history=history,
    )
    db.add(order)
    db.commit()
    return order


@pytest.fixture
def cenario(db_session, auth_headers):
    loja = make_store(db_session)
    compradora = make_user(db_session, "compradora@test.local")
    admin = make_user(db_session, "admin@test.local", is_admin=True)
    db_session.commit()
    return {
        "loja": loja,
        "compradora": compradora,
        "admin": admin,
        "como_compradora": auth_headers(compradora.id),
        "como_admin": auth_headers(admin.id, is_admin=True),
    }


@pytest.fixture
def reportar(client, cenario):
    def _reportar(
        order_id: int,
        reason: object = "danificado",
        description: object = TEXTO,
        headers: dict | None = None,
    ):
        return client.post(
            f"{ORDERS_URL}/{order_id}/complaints",
            json={"reason": reason, "description": description},
            headers=cenario["como_compradora"] if headers is None else headers,
        )

    return _reportar


# --- reportar --------------------------------------------------------------------


def test_comprador_reporta_dano_no_pedido_confirmado(db_session, cenario, reportar):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    resposta = reportar(pedido.id)

    assert resposta.status_code == 201
    body = resposta.json()
    assert (body["order_id"], body["reason"], body["description"]) == (
        pedido.id,
        "danificado",
        TEXTO,
    )
    assert body["created_at"]
    gravada = db_session.scalar(select(OrderComplaint))
    assert gravada is not None
    assert gravada.author_id == cenario["compradora"].id


@pytest.mark.parametrize(
    "aprovado_ha",
    [timedelta(hours=1), timedelta(days=1), timedelta(days=2), timedelta(days=4)],
    ids=["confirmado", "preparando", "enviado", "concluido"],
)
def test_reporta_do_confirmado_em_diante(db_session, cenario, reportar, aprovado_ha):
    pedido = make_order(
        db_session, cenario["compradora"], cenario["loja"], aprovado_ha=aprovado_ha
    )

    assert reportar(pedido.id, "nao_recebido").status_code == 201


def test_texto_perde_os_espacos_das_pontas(db_session, cenario, reportar):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    resposta = reportar(pedido.id, description=f"   {TEXTO}  ")

    assert resposta.json()["description"] == TEXTO


def test_pedido_aguardando_comprovante_recebe_409(db_session, cenario, reportar):
    pedido = make_order(
        db_session, cenario["compradora"], cenario["loja"], aprovado_ha=None
    )

    resposta = reportar(pedido.id)

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "COMPLAINT_NOT_ALLOWED"
    assert db_session.scalars(select(OrderComplaint)).all() == []


def test_pedido_de_outra_pessoa_responde_404(
    db_session, cenario, reportar, auth_headers
):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])
    curiosa = make_user(db_session, "curiosa@test.local")
    db_session.commit()

    resposta = reportar(pedido.id, headers=auth_headers(curiosa.id))

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert db_session.scalars(select(OrderComplaint)).all() == []


def test_pedido_inexistente_responde_404(cenario, reportar):
    resposta = reportar(999_999)

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_segunda_reclamacao_no_mesmo_pedido_responde_409(db_session, cenario, reportar):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])
    reportar(pedido.id, "nao_recebido", "Não chegou.")

    resposta = reportar(pedido.id, "danificado", "Agora chegou rasgada.")

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "ALREADY_REPORTED"
    assert db_session.scalars(select(OrderComplaint.reason)).all() == ["nao_recebido"]


@pytest.mark.parametrize("motivo", ["perdido", "", None, "NAO_RECEBIDO"])
def test_motivo_fora_dos_dois_valores_recebe_422(db_session, cenario, reportar, motivo):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    resposta = reportar(pedido.id, motivo)

    assert resposta.status_code == 422
    assert db_session.scalars(select(OrderComplaint)).all() == []


@pytest.mark.parametrize("texto", ["", "    ", None, "x" * 1001])
def test_texto_vazio_ou_longo_demais_recebe_422(db_session, cenario, reportar, texto):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    assert reportar(pedido.id, description=texto).status_code == 422


def test_reportar_exige_login(client, db_session, cenario):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    resposta = client.post(
        f"{ORDERS_URL}/{pedido.id}/complaints",
        json={"reason": "danificado", "description": TEXTO},
    )

    assert resposta.status_code == 401


def test_banco_recusa_motivo_fora_dos_dois_valores(db_session, cenario):
    """O CHECK está no banco, e não só no schema."""
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])

    db_session.add(
        OrderComplaint(
            order_id=pedido.id,
            author_id=cenario["compradora"].id,
            reason="perdido",
            description=TEXTO,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# --- a administradora lista ------------------------------------------------------


def test_administradora_lista_com_os_dados_do_pedido(
    client, db_session, cenario, reportar
):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])
    reportar(pedido.id, "nao_recebido", "Passou do prazo e nada chegou.")

    resposta = client.get(ADMIN_URL, headers=cenario["como_admin"])

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["total"] == 1
    entrada = body["items"][0]
    assert entrada["reason"] == "nao_recebido"
    assert entrada["description"] == "Passou do prazo e nada chegou."
    assert entrada["buyer"]["email"] == "compradora@test.local"
    assert entrada["order"]["id"] == pedido.id
    assert entrada["order"]["status"] == "confirmado"
    assert entrada["order"]["total_amount"] == 100.0
    assert entrada["order"]["store"]["name"] == "Aurora"
    assert [i["name"] for i in entrada["order"]["items"]] == ["Jaqueta"]


def test_lista_vazia_sem_reclamacao(client, cenario):
    resposta = client.get(ADMIN_URL, headers=cenario["como_admin"])

    assert resposta.status_code == 200
    assert resposta.json()["items"] == []


@pytest.mark.parametrize("quem", ["como_compradora", None])
def test_so_a_administradora_lista(client, cenario, quem):
    headers = cenario[quem] if quem else {}

    resposta = client.get(ADMIN_URL, headers=headers)

    assert resposta.status_code in (401, 403)
    if quem:
        assert resposta.json()["error"]["code"] == "ADMIN_REQUIRED"


# --- a loja e a peça não mostram nada --------------------------------------------


def test_rotas_publicas_nao_trazem_a_reclamacao(client, db_session, cenario, reportar):
    pedido = make_order(db_session, cenario["compradora"], cenario["loja"])
    reportar(pedido.id, "danificado", TEXTO)
    peca_id = pedido.items[0].product_id
    loja_id = cenario["loja"].id

    for caminho in (
        f"/api/stores/{loja_id}",
        f"/api/stores/{loja_id}/products",
        "/api/stores",
        f"/api/products/{peca_id}",
        "/api/products",
    ):
        resposta = client.get(caminho)
        assert resposta.status_code == 200, caminho
        texto = resposta.text.lower()
        assert TEXTO.lower() not in texto, caminho
        assert "complaint" not in texto, caminho
        assert "reclama" not in texto, caminho
